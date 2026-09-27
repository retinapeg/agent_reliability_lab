# camel_to_snake

Implement `camel_to_snake(name: str) -> str` in `solution.py`.

- Insert `_` before an uppercase ASCII letter when it is (a) preceded by a lowercase letter or a
  digit, or (b) preceded by an uppercase letter and followed by a lowercase letter. Then lowercase
  the whole string.
- Acronyms stay together: `"HTTPServer"` -> `"http_server"`,
  `"getHTTPResponseCode"` -> `"get_http_response_code"`, `"ABC"` -> `"abc"`.
- `"version2Update"` -> `"version2_update"`. Already-snake-case input and `""` are returned unchanged.
