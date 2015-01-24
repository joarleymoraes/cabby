import pytest
import urllib2

import httpretty

from itertools import ifilter

from taxii_client import create_client
from taxii_client import exceptions as exc

from libtaxii import messages_11 as tm11
from libtaxii.constants import *
from fixtures11 import *

### Utils

def create_client_11(**kwargs):
    client = create_client(HOST, version="1.1", **kwargs)
    return client


def register_uri(uri, body, **kwargs):
    httpretty.register_uri(httpretty.POST, uri, body=body, content_type='application/xml',
            adding_headers={'X-TAXII-Content-Type': VID_TAXII_XML_11}, **kwargs)


def get_sent_message():
    body = httpretty.last_request().body
    return tm11.get_message_from_xml(body)

### Tests

def test_no_discovery_path():
    client = create_client_11()

    with pytest.raises(exc.NoURIProvidedError):
        client.discover_services()


def test_no_discovery_path_when_pushing():
    client = create_client_11()

    with pytest.raises(exc.NoURIProvidedError):
        client.push(CONTENT, CONTENT_BINDING)


def test_incorrect_path():

    httpretty.enable()
    httpretty.register_uri(httpretty.POST, DISCOVERY_URI_HTTP, status=404)

    client = create_client_11(discovery_path=DISCOVERY_PATH)

    with pytest.raises(exc.UnsuccessfulStatusError):
        client.discover_services()


def test_discovery():

    httpretty.enable()
    register_uri(DISCOVERY_URI_HTTP, DISCOVERY_RESPONSE)

    client = create_client_11(discovery_path=DISCOVERY_PATH)

    services = client.discover_services()

    assert len(services) == 4

    assert len(filter(lambda s: s.service_type == SVC_INBOX, services)) == 1
    assert len(filter(lambda s: s.service_type == SVC_DISCOVERY, services)) == 2


    message = get_sent_message()

    assert type(message) == tm11.DiscoveryRequest


def test_discovery_https():

    httpretty.enable()
    register_uri(DISCOVERY_URI_HTTPS, DISCOVERY_RESPONSE)

    client = create_client_11(discovery_path=DISCOVERY_PATH, use_https=True)

    services = client.discover_services()

    assert len(services) == 4

    message = get_sent_message()
    assert type(message) == tm11.DiscoveryRequest


def test_collections():

    httpretty.enable()
    register_uri(COLLECTION_MANAGEMENT_URI, COLLECTION_MANAGEMENT_RESPONSE)

    client = create_client_11()

    response = client.get_collections(uri=COLLECTION_MANAGEMENT_PATH)

    assert len(response.collection_informations) == 2

    message = get_sent_message()
    assert type(message) == tm11.CollectionInformationRequest


def test_collections_with_automatic_discovery():

    httpretty.enable()
    register_uri(DISCOVERY_URI_HTTP, DISCOVERY_RESPONSE)
    register_uri(COLLECTION_MANAGEMENT_URI, COLLECTION_MANAGEMENT_RESPONSE)

    client = create_client_11(discovery_path=DISCOVERY_URI_HTTP)

    response = client.get_collections()

    assert len(response.collection_informations) == 2

    message = get_sent_message()
    assert type(message) == tm11.CollectionInformationRequest


def test_poll():

    httpretty.enable()
    register_uri(POLL_URI, POLL_RESPONSE)

    client = create_client_11()
    blocks = list(client.poll(POLL_COLLECTION, uri=POLL_PATH))

    assert len(blocks) == 2

    message = get_sent_message()
    assert type(message) == tm11.PollRequest
    assert message.collection_name == POLL_COLLECTION


def test_poll_with_subscription():

    httpretty.enable()
    register_uri(POLL_URI, POLL_RESPONSE)

    client = create_client_11()
    blocks = list(client.poll(POLL_COLLECTION, subscription_id=SUBSCRIPTION_ID, uri=POLL_PATH))

    assert len(blocks) == 2

    message = get_sent_message()
    assert type(message) == tm11.PollRequest
    assert message.collection_name == POLL_COLLECTION
    assert message.subscription_id == SUBSCRIPTION_ID


def test_poll_with_delivery():

    httpretty.enable()
    register_uri(DISCOVERY_URI_HTTP, DISCOVERY_RESPONSE)
    register_uri(POLL_URI, POLL_RESPONSE)

    client = create_client_11(discovery_path=DISCOVERY_PATH)

    services = client.discover_services()

    inbox = next(ifilter(lambda s: s.service_type == SVC_INBOX, services))

    blocks = list(client.poll(POLL_COLLECTION, inbox_service=inbox, uri=POLL_PATH))

    assert len(blocks) == 2

    message = get_sent_message()
    assert type(message) == tm11.PollRequest
    assert message.collection_name == POLL_COLLECTION
    assert message.poll_parameters.delivery_parameters.inbox_address == inbox.service_address
    assert message.poll_parameters.allow_asynch == True



def test_poll_prepared():

    httpretty.enable()
    register_uri(POLL_URI, POLL_RESPONSE)

    client = create_client_11()
    blocks = list(client.poll_prepared(POLL_COLLECTION, uri=POLL_PATH))

    assert len(blocks) == 2

    assert blocks[0].source_collection == POLL_COLLECTION

    assert blocks[0].content == CONTENT_BLOCKS[0]
    assert blocks[1].content == CONTENT_BLOCKS[1]

    message = get_sent_message()
    assert type(message) == tm11.PollRequest
    assert message.collection_name == POLL_COLLECTION


def test_poll_with_fullfilment():

    httpretty.enable()
    register_uri(POLL_URI, POLL_RESPONSE_WITH_MORE_1)

    client = create_client_11()

    gen = client.poll_prepared(POLL_COLLECTION, uri=POLL_PATH)
    block_1 = next(gen)

    assert block_1.content == CONTENT_BLOCKS[0]

    message = get_sent_message()
    assert type(message) == tm11.PollRequest
    assert message.collection_name == POLL_COLLECTION

    register_uri(POLL_URI, POLL_RESPONSE_WITH_MORE_2)
    block_2 = next(gen)
    
    assert block_2.content == CONTENT_BLOCKS[1]

    message = get_sent_message()
    assert type(message) == tm11.PollFulfillmentRequest
    assert message.collection_name == POLL_COLLECTION
    assert message.result_part_number == 2


def test_subscribe():

    httpretty.enable()
    register_uri(COLLECTION_MANAGEMENT_URI, SUBSCRIPTION_RESPONSE)

    client = create_client_11()
    response = client.subscribe(POLL_COLLECTION, uri=COLLECTION_MANAGEMENT_PATH)

    assert response.collection_name == POLL_COLLECTION

    message = get_sent_message()
    assert type(message) == tm11.ManageCollectionSubscriptionRequest
    assert message.collection_name == POLL_COLLECTION
    assert message.action == tm11.ACT_SUBSCRIBE


def test_subscribe_with_push():
    httpretty.enable()

    register_uri(COLLECTION_MANAGEMENT_URI, SUBSCRIPTION_RESPONSE)
    register_uri(DISCOVERY_URI_HTTP, DISCOVERY_RESPONSE)

    client = create_client_11(discovery_path=DISCOVERY_PATH)

    services = client.discover_services()

    inbox = next(ifilter(lambda s: s.service_type == SVC_INBOX, services))

    response = client.subscribe(POLL_COLLECTION, inbox_service=inbox, uri=COLLECTION_MANAGEMENT_PATH)

    assert response.collection_name == POLL_COLLECTION

    message = get_sent_message()
    assert type(message) == tm11.ManageCollectionSubscriptionRequest
    assert message.collection_name == POLL_COLLECTION
    assert message.delivery_parameters.inbox_address == inbox.service_address
    assert message.action == tm11.ACT_SUBSCRIBE



def test_subscribtion_status():

    httpretty.enable()
    register_uri(COLLECTION_MANAGEMENT_URI, SUBSCRIPTION_RESPONSE)

    client = create_client_11()

    response = client.get_subscription_status(POLL_COLLECTION, subscription_id=SUBSCRIPTION_ID,
            uri=COLLECTION_MANAGEMENT_PATH)

    assert response.collection_name == POLL_COLLECTION

    message = get_sent_message()
    assert type(message) == tm11.ManageCollectionSubscriptionRequest
    assert message.collection_name == POLL_COLLECTION
    assert message.action == tm11.ACT_STATUS


def test_unsubscribe():

    httpretty.enable()
    register_uri(COLLECTION_MANAGEMENT_URI, SUBSCRIPTION_RESPONSE)

    client = create_client_11()

    response = client.unsubscribe(POLL_COLLECTION, subscription_id=SUBSCRIPTION_ID,
            uri=COLLECTION_MANAGEMENT_PATH)

    assert response.collection_name == POLL_COLLECTION

    message = get_sent_message()
    assert type(message) == tm11.ManageCollectionSubscriptionRequest
    assert message.collection_name == POLL_COLLECTION
    assert message.action == tm11.ACT_UNSUBSCRIBE


def test_pause_subscription():

    httpretty.enable()
    register_uri(COLLECTION_MANAGEMENT_URI, SUBSCRIPTION_RESPONSE)

    client = create_client_11()

    response = client.pause_subscription(POLL_COLLECTION, subscription_id=SUBSCRIPTION_ID,
            uri=COLLECTION_MANAGEMENT_PATH)

    assert response.collection_name == POLL_COLLECTION

    message = get_sent_message()
    assert type(message) == tm11.ManageCollectionSubscriptionRequest
    assert message.collection_name == POLL_COLLECTION
    assert message.action == tm11.ACT_PAUSE


def test_resume_subscription():

    httpretty.enable()
    register_uri(COLLECTION_MANAGEMENT_URI, SUBSCRIPTION_RESPONSE)

    client = create_client_11()

    response = client.resume_subscription(POLL_COLLECTION, subscription_id=SUBSCRIPTION_ID,
            uri=COLLECTION_MANAGEMENT_PATH)

    assert response.collection_name == POLL_COLLECTION

    message = get_sent_message()
    assert type(message) == tm11.ManageCollectionSubscriptionRequest
    assert message.collection_name == POLL_COLLECTION
    assert message.action == tm11.ACT_RESUME


def test_push():

    httpretty.enable()
    register_uri(INBOX_URI, INBOX_RESPONSE)

    client = create_client_11()

    response = client.push(CONTENT, CONTENT_BINDING, uri=INBOX_URI)

    message = get_sent_message()

    assert type(message) == tm11.InboxMessage
    assert len(message.content_blocks) == 1
    assert message.content_blocks[0].content == CONTENT 
    assert message.content_blocks[0].content_binding.binding_id == CONTENT_BINDING


def test_push_with_destination():

    httpretty.enable()
    register_uri(INBOX_URI, INBOX_RESPONSE)

    client = create_client_11()

    dest_collections = [POLL_COLLECTION]

    response = client.push(CONTENT, CONTENT_BINDING, collections=dest_collections, uri=INBOX_URI)

    message = get_sent_message()

    assert type(message) == tm11.InboxMessage
    assert len(message.content_blocks) == 1
    assert message.content_blocks[0].content == CONTENT 
    assert message.content_blocks[0].content_binding.binding_id == CONTENT_BINDING

    assert message.destination_collection_names == dest_collections





