import config
import requests

url = f"https://api.telegram.org/bot{config.BOT_TOKEN}/deleteWebhook"
resp = requests.post(url)
print(resp.status_code, resp.text)
