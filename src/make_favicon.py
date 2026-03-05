# filename: make_favicon.py
import base64
data = b"""
AAABAAMAEBAAAAEAIABoBAAAFgAAACgAAAAQAAAAIAAAAAEAGAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAD///8A////AP///wD///8A////AP///wD///8A////AP///wD///8A////AP///wD///8A
////AP///wD///8A////AP///wD///8A////AP///wD///8A////AP///wD///8AAAAAAAAAAAAA
AAAAAA=="""
open("favicon.ico","wb").write(base64.b64decode(data))
print("favicon.ico written")

