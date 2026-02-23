"""Проверка доступности OpenAI и DeepSeek API с текущими ключами."""
import requests
import config


def check_openai():
    key = config.OPENAI_API_KEY
    if not key:
        print('OPENAI_API_KEY not set')
        return
    try:
        r = requests.get('https://api.openai.com/v1/models', headers={'Authorization': f'Bearer {key}'}, timeout=10)
        print('OpenAI:', r.status_code, r.text[:300])
    except Exception as e:
        print('OpenAI request failed:', e)


def check_deepseek():
    key = config.DEEPSEEK_API_KEY
    url = config.DEEPSEEK_BASE_URL.rstrip('/') + '/v1/models'
    if not key:
        print('DEEPSEEK_API_KEY not set')
        return
    try:
        r = requests.get(url, headers={'Authorization': f'Bearer {key}'}, timeout=10)
        print('DeepSeek:', r.status_code, r.text[:300])
    except Exception as e:
        print('DeepSeek request failed:', e)


if __name__ == '__main__':
    print('Checking API connectivity...')
    check_openai()
    check_deepseek()
