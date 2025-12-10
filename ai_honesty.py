# ai_honesty.py
# Система предотвращения AI галлюцинаций
# Version: 0.25.0

import re
import json
from typing import Dict, List, Tuple, Optional
from enum import Enum

# ============================================================================
# CONFIDENCE LEVELS
# ============================================================================
class ConfidenceLevel(Enum):
    VERY_HIGH = 0.95  # 95%+
    HIGH = 0.8       # 80-95%
    MEDIUM = 0.6     # 60-80%
    LOW = 0.4        # 40-60%
    VERY_LOW = 0.2   # 20-40%
    UNCERTAIN = 0.0  # < 20%

# ============================================================================
# FABRICATION PATTERNS
# ============================================================================
# Паттерны, которые указывают на возможную галлюцинацию
FABRICATION_PATTERNS = {
    # Придуманные инвесторы/компании
    "fake_investors": [
        r"инвестор\s+\w+\s+\w+",
        r"фонд\s+\w+\s+capital",
        r"компания\s+\w+\s+inc",
        r"startup\s+\w+\s+\w+",
    ],
    
    # Точные финансовые цифры без источника
    "suspicious_numbers": [
        r"стоимость.*?(\$|€|₽)?\s*[\d.]+\s*(миллион|миллиард|тысяч)",
        r"привлекли.*?(\$|€|₽)?\s*[\d.]+\s*(млн|млрд)",
        r"доход.*?(\$|€|₽)?\s*[\d.]+\s*(млн|млрд)",
    ],
    
    # Специфические названия без источников
    "specific_names": [
        r"генеральный\s+директор\s+\w+\s+\w+",
        r"основатель\s+\w+\s+\w+",
        r"ceo\s+\w+\s+\w+",
        r"председатель\s+\w+\s+\w+",
    ],
    
    # Слишком уверенные утверждения
    "overconfident": [
        r"точно\s+известно",
        r"абсолютно\s+ясно",
        r"совершенно\s+очевидно",
        r"гарантированно",
        r"100%\s+будет",
    ]
}

# ============================================================================
# RELIABLE SOURCES
# ============================================================================
RELIABLE_SOURCES = {
    "official": [
        "официальный сайт",
        "official website",
        "press release",
        "пресс-релиз",
        "Reuters",
        "Bloomberg",
        "Financial Times",
        "SEC filing",
        "EDGAR",
    ],
    "credible": [
        "согласно",
        "по данным",
        "по словам",
        "в интервью",
        "в заявлении",
        "опубликовано",
    ],
}

# ============================================================================
# HONESTY DETECTION SYSTEM
# ============================================================================
class HonestyDetector:
    """Система обнаружения и предотвращения галлюцинаций"""
    
    def __init__(self):
        self.suspicious_patterns = []
        self.confidence_score = 1.0
        self.warnings = []
    
    def analyze_response(self, response: str) -> Dict:
        """Анализировать ответ AI на честность"""
        self.suspicious_patterns = []
        self.warnings = []
        self.confidence_score = 1.0
        
        # Проверка на каждый тип галлюцинации
        self._check_fabrications(response)
        self._check_missing_sources(response)
        self._check_overconfidence(response)
        self._check_specificity(response)
        
        return {
            "is_honest": self.confidence_score > 0.6,
            "confidence": self.confidence_score,
            "warnings": self.warnings,
            "patterns_detected": len(self.suspicious_patterns),
            "details": self.suspicious_patterns,
        }
    
    def _check_fabrications(self, response: str):
        """Проверить на придуманные факты"""
        for pattern_type, patterns in FABRICATION_PATTERNS.items():
            for pattern in patterns:
                matches = re.finditer(pattern, response, re.IGNORECASE)
                for match in matches:
                    self._add_warning(
                        f"⚠️ Возможная галлюцинация типа '{pattern_type}'",
                        match.group(),
                        severity="medium"
                    )
                    self.confidence_score *= 0.8  # Снижаем уверенность на 20%
    
    def _check_missing_sources(self, response: str):
        """Проверить, есть ли ссылки на источники"""
        has_sources = any(
            re.search(source, response, re.IGNORECASE)
            for sources in RELIABLE_SOURCES.values()
            for source in sources
        )
        
        # Если делаются утверждения без источников
        if not has_sources and any(
            re.search(pattern, response, re.IGNORECASE)
            for patterns in FABRICATION_PATTERNS.values()
            for pattern in patterns
        ):
            self._add_warning(
                "⚠️ Утверждение сделано без указания источника",
                "Добавьте ссылку на источник информации",
                severity="high"
            )
            self.confidence_score *= 0.7  # Снижаем на 30%
    
    def _check_overconfidence(self, response: str):
        """Проверить на чрезмерную уверенность"""
        for pattern_type, patterns in FABRICATION_PATTERNS.items():
            if pattern_type == "overconfident":
                for pattern in patterns:
                    if re.search(pattern, response, re.IGNORECASE):
                        self._add_warning(
                            "⚠️ Слишком уверенное утверждение",
                            "AI может ошибаться - используйте 'вероятно', 'возможно'",
                            severity="medium"
                        )
                        self.confidence_score *= 0.85
    
    def _check_specificity(self, response: str):
        """Проверить на чрезмерную специфичность"""
        # Если много очень специфичных деталей, это может быть красный флаг
        specific_count = sum(
            len(re.findall(pattern, response, re.IGNORECASE))
            for patterns in FABRICATION_PATTERNS.values()
            for pattern in patterns
        )
        
        if specific_count > 5:
            self._add_warning(
                "⚠️ Много специфичных деталей - возможна галлюцинация",
                "Проверьте ключевые факты вручную",
                severity="high"
            )
            self.confidence_score *= 0.75
    
    def _add_warning(self, message: str, detail: str, severity: str = "low"):
        """Добавить предупреждение"""
        self.warnings.append({
            "message": message,
            "detail": detail,
            "severity": severity,
        })
        self.suspicious_patterns.append({
            "type": message,
            "example": detail[:100],
        })

# ============================================================================
# RESPONSE CLEANING & SANITIZATION
# ============================================================================
class ResponseCleaner:
    """Очистить и нормализовать ответ AI"""
    
    @staticmethod
    def clean_response(response: str, remove_hallucinations: bool = True) -> str:
        """
        Очистить ответ от потенциальных галлюцинаций
        """
        # 1. Убрать звездочки и форматирование
        response = response.replace("*", "").replace("**", "")
        
        # 2. Заменить чрезмерно уверенные фразы
        response = ResponseCleaner._soften_claims(response)
        
        # 3. Удалить придуманные источники
        if remove_hallucinations:
            response = ResponseCleaner._remove_fake_citations(response)
        
        # 4. Добавить дисклеймер если нужно
        response = ResponseCleaner._add_disclaimer_if_needed(response)
        
        return response.strip()
    
    @staticmethod
    def _soften_claims(response: str) -> str:
        """Смягчить слишком уверенные утверждения"""
        replacements = {
            r"(?i)(точно известно|точно|гарантированно)": "вероятно,",
            r"(?i)(абсолютно ясно|совершенно очевидно)": "похоже,",
            r"(?i)(100% будет|definitely будет)": "возможно, произойдет",
            r"(?i)(никогда не)": "маловероятно, что",
            r"(?i)(всегда)": "в большинстве случаев",
        }
        
        for pattern, replacement in replacements.items():
            response = re.sub(pattern, replacement, response)
        
        return response
    
    @staticmethod
    def _remove_fake_citations(response: str) -> str:
        """Удалить ложные ссылки на источники"""
        # Удалить паттерны типа "по данным компании X" если это неизвестная компания
        response = re.sub(
            r"(?i)по\s+данным\s+(компании\s+)?\w{1,3}\b",
            "",
            response
        )
        
        return response
    
    @staticmethod
    def _add_disclaimer_if_needed(response: str) -> str:
        """Добавить дисклеймер если есть неопределенность"""
        if any(keyword in response.lower() for keyword in ["возможно", "вероятно", "примерно", "может быть"]):
            disclaimer = "\n\n⚠️ Это предварительный анализ. Проверьте ключевые факты в официальных источниках."
            if disclaimer not in response:
                response += disclaimer
        
        return response

# ============================================================================
# HONESTY RULES & CHECKS
# ============================================================================
class HonestyRules:
    """Набор правил для поддержания честности AI"""
    
    # Правила, которые должны быть в системном промпте
    SYSTEM_RULES = """
КРИТИЧЕСКИЕ ПРАВИЛА ЧЕСТНОСТИ:

1. НИКОГДА НЕ ВЫДУМЫВАЙ ФАКТЫ:
   - Если не знаешь точный источник информации, скажи об этом
   - Если не знаешь имена реальных людей, не придумывай их
   - Если не уверен в цифрах, скажи "примерно", "в районе", "около"

2. ВСЕГДА УКАЗЫВАЙ ИСТОЧНИКИ:
   - "согласно X", "по данным X", "в статье X"
   - Если источника нет, скажи "я не нашел точных данных, но..."
   - Известные факты могут быть без источников

3. ИСПОЛЬЗУЙ МЯГКИЕ ФОРМУЛИРОВКИ:
   ❌ "Точно произойдет"
   ✅ "Вероятно произойдет"
   
   ❌ "Инвестор X вложил $100M"
   ✅ "По данным источников, в компанию вложили примерно $100M"

4. КОГДА НЕ УВЕРЕН:
   ✅ "Я не знаю" > ✅ "Не уверен" > ❌ "Выдуман факт"
   
   Всегда лучше признать незнание, чем выдумать неправду

5. КОДА ГОВОРИШЬ О ЛЮДЯХ/КОМПАНИЯХ:
   - Только проверенные факты
   - Только из авторитетных источников
   - С указанием источника

6. ФИНАНСОВАЯ ИНФОРМАЦИЯ:
   - Никогда не выдумывай цены, суммы инвестиций, доходы
   - Используй "примерно", "в районе", "около"
   - Указывай дату информации

7. КОГДА АНАЛИЗИРУЕШЬ НОВОСТЬ:
   - Выделяй ФАКТЫ (с источниками)
   - Выделяй ПРЕДПОЛОЖЕНИЯ (свои или из текста)
   - Выделяй НЕИЗВЕСТНОЕ (что нам неизвестно)
"""
    
    @staticmethod
    def get_honesty_prompt() -> str:
        """Получить промпт для обеспечения честности"""
        return HonestyRules.SYSTEM_RULES
    
    @staticmethod
    def validate_honesty(response: str, confidence_threshold: float = 0.6) -> Tuple[bool, str]:
        """Проверить ответ на честность"""
        detector = HonestyDetector()
        analysis = detector.analyze_response(response)
        
        if analysis["confidence"] < confidence_threshold:
            warning_text = "\n".join([
                w["message"] for w in analysis["warnings"]
            ])
            return False, f"⚠️ ВОЗМОЖНАЯ ГАЛЛЮЦИНАЦИЯ:\n{warning_text}"
        
        return True, "✅ Ответ честный и надежный"

# ============================================================================
# FALLBACK RESPONSES FOR UNCERTAIN TOPICS
# ============================================================================
FALLBACK_TEMPLATES = {
    "unknown_person": "Я не могу подтвердить информацию об этом человеке. Пожалуйста, проверьте официальные источники.",
    
    "unknown_company": "Я не нашел информацию об этой компании. Это может быть частная компания, стартап или вновь созданная организация.",
    
    "uncertain_facts": "На основе доступной информации я не могу дать точный ответ. Рекомендую проверить источник новости.",
    
    "speculation": "Это предположение, а не подтвержденный факт. Ожидайте официального подтверждения.",
    
    "no_data": "К сожалению, у меня нет достаточных данных для полного анализа. Попробуйте отправить больше контекста.",
}

# ============================================================================
# EXPORT FUNCTIONS
# ============================================================================
def analyze_ai_response(response: str) -> Dict:
    """Быстрый анализ ответа AI на честность"""
    detector = HonestyDetector()
    return detector.analyze_response(response)

def clean_ai_response(response: str) -> str:
    """Очистить ответ от галлюцинаций"""
    cleaner = ResponseCleaner()
    return cleaner.clean_response(response)

def get_honesty_system_prompt() -> str:
    """Получить системный промпт для честности"""
    return HonestyRules.get_honesty_prompt()

def validate_response(response: str, min_confidence: float = 0.6) -> bool:
    """Проверить, достаточно ли честный ответ"""
    is_honest, _ = HonestyRules.validate_honesty(response, min_confidence)
    return is_honest
