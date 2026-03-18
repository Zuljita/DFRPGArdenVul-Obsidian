import subprocess
import json

prompt = "Extract key nouns from: 'The brave knight Arthur went to the Great Cavern to find the Sword of Light.'"
result = subprocess.run(['gemini', '-m', 'gemini-2.5-flash', prompt], capture_output=True, text=True, timeout=30)
print(result.stdout)
