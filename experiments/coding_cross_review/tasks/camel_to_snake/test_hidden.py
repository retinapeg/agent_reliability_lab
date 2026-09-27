from solution import camel_to_snake


def test_acronyms():
    assert camel_to_snake("HTTPServer") == "http_server"
    assert camel_to_snake("getHTTPResponseCode") == "get_http_response_code"
    assert camel_to_snake("ABC") == "abc"


def test_digits():
    assert camel_to_snake("version2Update") == "version2_update"


def test_unchanged():
    assert camel_to_snake("already_snake") == "already_snake"
    assert camel_to_snake("") == ""
