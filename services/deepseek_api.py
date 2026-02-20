"""
Сервис для работы с DeepSeek API
"""
import json
import requests
from typing import Dict, List, Optional
import config


class DeepSeekService:
    """Сервис для анализа текста через DeepSeek API"""
    
    def __init__(self):
        self.api_key = config.DEEPSEEK_API_KEY
        self.base_url = config.DEEPSEEK_BASE_URL
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
    
    def analyze_expense(self, text: str, categories: List[Dict]) -> Dict:
        """
        Анализ текста расхода/дохода
        """
        categories_text = "\n".join([
            f"- {cat['name']} ({cat['emoji']}): {', '.join(cat.get('subcategories', []))}"
            for cat in categories
        ])
        
        prompt = f"""Проанализируй сообщение пользователя и извлеки информацию о финансовой операции.

Сообщение: "{text}"

Доступные категории:
{categories_text}

Верни ответ СТРОГО в формате JSON:
{{
    "amount": число (сумма операции),
    "description": "название товара/услуги (например: картошка, бензин, куртка)",
    "category": "название категории из списка выше",
    "subcategory": "название товара/услуги (то же что description, например: картошка, бензин, куртка)"
}}

ВАЖНО:
- "description" и "subcategory" = конкретное название товара или услуги из сообщения
- "category" = подходящая категория из списка выше
- Например: "100 картошка" → description="картошка", category="Продукты", subcategory="картошка"
- Например: "500 бензин" → description="бензин", category="Авто", subcategory="бензин"
- Если не можешь определить категорию, используй null для category
Ответ должен быть ТОЛЬКО JSON, без дополнительного текста."""

        try:
            response = requests.post(
                f"{self.base_url}/v1/chat/completions",
                headers=self.headers,
                json={
                    "model": "deepseek-chat",
                    "messages": [
                        {"role": "system", "content": "Ты - помощник для анализа финансовых операций. Отвечай только в формате JSON."},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.3
                },
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                content = result['choices'][0]['message']['content']
                try:
                    start_idx = content.find('{')
                    end_idx = content.rfind('}') + 1
                    if start_idx != -1 and end_idx > start_idx:
                        json_str = content[start_idx:end_idx]
                        return json.loads(json_str)
                    else:
                        return self._fallback_parse(text)
                except json.JSONDecodeError:
                    return self._fallback_parse(text)
            else:
                return self._fallback_parse(text)
                
        except Exception as e:
            print(f"Ошибка при обращении к DeepSeek API: {e}")
            return self._fallback_parse(text)
    
    def _fallback_parse(self, text: str) -> Dict:
        """Резервный парсинг без ИИ"""
        import re
        numbers = re.findall(r'\d+(?:\.\d+)?', text)
        amount = float(numbers[0]) if numbers else 0.0
        description = re.sub(r'\d+(?:\.\d+)?', '', text).strip()
        description = re.sub(r'рубл[ейя]*|₽|руб', '', description, flags=re.IGNORECASE).strip()
        return {
            "amount": amount,
            "description": description or "Без описания",
            "category": None,
            "subcategory": None
        }
    
    def analyze_receipt_image(self, image_data: bytes, categories: List[Dict], image_url: str = None) -> List[Dict]:
        """
        Анализ изображения чека через OpenAI GPT-4o Vision
        """
        import base64
        import config as cfg
        
        if not cfg.OPENAI_API_KEY:
            print("OPENAI_API_KEY не задан, пробуем OCR")
            return self._analyze_via_ocr(image_data, categories)
        
        # Кодируем изображение в base64
        image_base64 = base64.b64encode(image_data).decode('utf-8')
        
        categories_text = "\n".join([
            f"- {cat['name']} ({cat['emoji']}): {', '.join(cat.get('subcategories', []))}"
            for cat in categories
        ])
        
        prompt = f"""На изображении кассовый чек. Прочитай все товары и их цены.

Доступные категории для классификации:
{categories_text}

Верни ТОЛЬКО JSON массив (без markdown, без пояснений):
[
    {{
        "name": "название товара",
        "amount": число,
        "category": "категория из списка",
        "subcategory": "подкатегория из списка"
    }}
]

Правила:
- Включай только товары с ценами
- Не включай итоги, скидки, налоги, сдачу
- amount — число (не строка)
- Если категория неизвестна — null"""

        try:
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {cfg.OPENAI_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "gpt-4o",
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/jpeg;base64,{image_base64}",
                                        "detail": "high"
                                    }
                                },
                                {
                                    "type": "text",
                                    "text": prompt
                                }
                            ]
                        }
                    ],
                    "max_tokens": 2000,
                    "temperature": 0.1
                },
                timeout=60
            )
            
            print(f"OpenAI Vision status: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                content = result['choices'][0]['message']['content']
                print(f"OpenAI Vision ответ: {content[:500]}")
                
                try:
                    # Убираем markdown если есть
                    content = content.strip()
                    if content.startswith('```'):
                        content = content.split('```')[1]
                        if content.startswith('json'):
                            content = content[4:]
                    
                    start_idx = content.find('[')
                    end_idx = content.rfind(']') + 1
                    if start_idx != -1 and end_idx > start_idx:
                        parsed = json.loads(content[start_idx:end_idx])
                        valid = [i for i in parsed if i.get('amount') and float(i.get('amount', 0)) > 0]
                        return valid
                except (json.JSONDecodeError, ValueError) as e:
                    print(f"JSON parse error: {e}, content: {content[:200]}")
            else:
                print(f"OpenAI error {response.status_code}: {response.text[:300]}")
                
        except Exception as e:
            print(f"OpenAI Vision exception: {e}")
        
        return []
    
    def _analyze_via_ocr(self, image_data: bytes, categories: List[Dict]) -> List[Dict]:
        """Fallback: OCR через easyocr → DeepSeek"""
        try:
            import easyocr
            import numpy as np
            from PIL import Image
            import io
            
            if not hasattr(self, '_easyocr_reader'):
                print("Инициализация EasyOCR...")
                self._easyocr_reader = easyocr.Reader(['ru', 'en'], gpu=False)
            
            image = Image.open(io.BytesIO(image_data))
            if image.mode != 'RGB':
                image = image.convert('RGB')
            img_array = np.array(image)
            results = self._easyocr_reader.readtext(img_array)
            text = '\n'.join([item[1] for item in results])
            
            if text and len(text.strip()) > 20:
                return self.analyze_receipt(text, categories)
        except Exception as e:
            print(f"OCR fallback ошибка: {e}")
        
        return []

    def analyze_receipt(self, receipt_text: str, categories: List[Dict]) -> List[Dict]:
        """
        Анализ текста чека через DeepSeek
        """
        categories_text = "\n".join([
            f"- {cat['name']} ({cat['emoji']}): {', '.join(cat.get('subcategories', []))}"
            for cat in categories
        ])
        
        prompt = f"""Проанализируй текст чека и извлеки список товаров с ценами.

Текст чека:
{receipt_text}

Доступные категории:
{categories_text}

Верни ответ СТРОГО в формате JSON (массив товаров):
[
    {{
        "name": "название товара",
        "amount": число (цена),
        "category": "категория",
        "subcategory": "подкатегория"
    }}
]

Ответ должен быть ТОЛЬКО JSON массив, без дополнительного текста."""

        try:
            response = requests.post(
                f"{self.base_url}/v1/chat/completions",
                headers=self.headers,
                json={
                    "model": "deepseek-chat",
                    "messages": [
                        {"role": "system", "content": "Ты - помощник для анализа чеков. Отвечай только в формате JSON."},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.3
                },
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                content = result['choices'][0]['message']['content']
                try:
                    start_idx = content.find('[')
                    end_idx = content.rfind(']') + 1
                    if start_idx != -1 and end_idx > start_idx:
                        json_str = content[start_idx:end_idx]
                        return json.loads(json_str)
                    else:
                        return []
                except json.JSONDecodeError:
                    return []
            else:
                return []
                
        except Exception as e:
            print(f"Ошибка при обращении к DeepSeek API: {e}")
            return []
