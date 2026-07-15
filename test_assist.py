import requests
import json

data = {
    "assistType": "optimize",
    "existingCode": "import pandas as pd\ndf = pd.DataFrame({'a':[1,2,3]})\nprint(df)",
    "language": "python",
    "prompt": "帮我优化"
}

r = requests.post('http://127.0.0.1:8000/model/code/assist', json=data, timeout=60, stream=True)
print('status:', r.status_code)
for line in r.iter_lines(decode_unicode=True):
    if line:
        print(line[:200])