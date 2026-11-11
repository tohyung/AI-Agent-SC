"""One tiny Gemini request with the current key, to check a key works (prints no key)."""
from research.adapters.model_transport import ModelTransport

transport = ModelTransport(provider="gemini", api_style="chat", max_tokens=50, disable_reasoning=True,
                           request_json_object=False)
print(transport.generate("Return a JSON object.", 'Reply with {"ok": true}'), transport.model)
