"""One tiny Gemini request with the current key; prints a short hash of the key, never the key."""
import hashlib
import os

from research.adapters.model_transport import ModelTransport

transport = ModelTransport(provider="gemini", api_style="chat", max_tokens=50, disable_reasoning=True,
                           request_json_object=False)
key = os.environ.get("GEMINI_API_KEY", "")
print(transport.generate("Return a JSON object.", 'Reply with {"ok": true}'), transport.model,
      "key", hashlib.sha256(key.encode()).hexdigest()[:8])
