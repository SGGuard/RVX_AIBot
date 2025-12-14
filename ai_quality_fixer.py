"""
AI Quality Fixer v0.1.0 - Улучшение качества ответов AI
=========================================================

Решает основные проблемы с качеством анализа от AI:
1. Улучшенный промпт с конкретными примерами
2. Строгая валидация выхода
3. Smart retry-логика для плохих ответов
4. Post-processing для нормализации
"""

import json
import logging
from typing import Dict, Any, Optional, Tuple, List
from dataclasses import dataclass

logger = logging.getLogger("AI_QUALITY")


@dataclass
class AnalysisQuality:
    """Score для оценки качества анализа."""
    score: float  # 0-10
    issues: List[str]
    is_valid: bool
    confidence: float


class AIQualityValidator:
    """Валидирует и улучшает качество ответов от AI."""
    
    # Минимальные требования к качеству
    MIN_SUMMARY_LENGTH = 50  # символов
    MAX_SUMMARY_LENGTH = 500
    MIN_IMPACT_POINTS = 2
    MAX_IMPACT_POINTS = 5
    
    # Плохие паттерны - признаки некачественного ответа
    BAD_PATTERNS = [
        'это зависит от',
        'может быть',
        'возможно',
        'предположительно',
        'по мнению некоторых',
        'некоторые эксперты считают',
        'обычно',
        'как правило',
        'в целом',
        'в большинстве случаев',
    ]
    
    # Хорошие паттерны - признаки качественного анализа
    GOOD_PATTERNS = [
        'это означает',
        'конкретный результат',
        'уровень поддержки',
        'уровень сопротивления',
        'тренд',
        'прорыв',
        'доля рынка',
        'объем торговли',
        'волатильность',
    ]
    
    @classmethod
    def validate_analysis(cls, data: Any) -> AnalysisQuality:
        """Проверяет качество анализа от AI.
        
        Args:
            data: Ответ от AI (должен быть dict)
            
        Returns:
            AnalysisQuality с оценкой и списком проблем
        """
        issues = []
        score = 5.0  # Начинаем с базовой оценки 5.0, потом добавляем/вычитаем
        
        # 1. Базовая структура
        if not isinstance(data, dict):
            return AnalysisQuality(
                score=0.0,
                issues=['Ответ не является JSON объектом'],
                is_valid=False,
                confidence=0.0
            )
        
        # 2. Проверяем обязательные поля
        if 'summary_text' not in data or not data['summary_text']:
            issues.append('Отсутствует или пуст summary_text')
            score -= 3.0
        else:
            summary = str(data['summary_text']).strip()
            
            # Длина
            if len(summary) < cls.MIN_SUMMARY_LENGTH:
                issues.append(f'summary_text слишком короткий ({len(summary)} < {cls.MIN_SUMMARY_LENGTH})')
                score -= 1.5
            elif len(summary) > cls.MAX_SUMMARY_LENGTH:
                issues.append(f'summary_text слишком длинный ({len(summary)} > {cls.MAX_SUMMARY_LENGTH})')
                score -= 1.0
            else:
                score += 1.0
            
            # Плохие паттерны = неопределённость
            bad_count = sum(1 for pattern in cls.BAD_PATTERNS 
                          if pattern.lower() in summary.lower())
            if bad_count > 0:
                issues.append(f'Найдено {bad_count} паттернов неопределённости')
                score -= bad_count * 1.0  # Более строго штрафуем за воду
            
            # Хорошие паттерны = конкретность
            good_count = sum(1 for pattern in cls.GOOD_PATTERNS 
                           if pattern.lower() in summary.lower())
            if good_count > 0:
                score += good_count * 0.5
        
        # 3. Impact points
        if 'impact_points' not in data:
            issues.append('Отсутствует impact_points')
            score -= 3.0
        else:
            points = data['impact_points']
            
            if not isinstance(points, list):
                issues.append('impact_points должен быть списком')
                score -= 2.0
            elif len(points) < cls.MIN_IMPACT_POINTS:
                issues.append(f'Недостаточно impact points ({len(points)} < {cls.MIN_IMPACT_POINTS})')
                score -= 1.5
            elif len(points) > cls.MAX_IMPACT_POINTS:
                issues.append(f'Слишком много impact points ({len(points)} > {cls.MAX_IMPACT_POINTS})')
                score -= 1.0
            else:
                score += 1.5
                
                # Проверяем каждый пункт
                for i, point in enumerate(points):
                    if not isinstance(point, str):
                        issues.append(f'impact_points[{i}] не строка')
                        score -= 0.5
                    elif len(point.strip()) < 10:
                        issues.append(f'impact_points[{i}] слишком короткий')
                        score -= 0.3
                    else:
                        score += 0.2
        
        # 4. Опциональные поля
        has_action = 'action' in data and data['action'] in ['BUY', 'HOLD', 'SELL', 'WATCH']
        if has_action:
            score += 0.5
        
        has_risk = 'risk_level' in data and data['risk_level'] in ['Low', 'Medium', 'High']
        if has_risk:
            score += 0.5
        
        # 5. Общий анализ
        if 'simplified_text' in data or 'learning_question' in data:
            score += 0.5
        
        # Финальная оценка (5.0+ считается валидным, но есть проблемы)
        is_valid = score >= 4.0 and len(issues) < 4
        confidence = min(1.0, max(0.0, (score + 1.0) / 11.0))
        
        return AnalysisQuality(
            score=max(0.0, score),
            issues=issues,
            is_valid=is_valid,
            confidence=confidence
        )
    
    @classmethod
    def fix_analysis(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """Пытается исправить неправильный анализ от AI.
        
        Args:
            data: Неправильный анализ
            
        Returns:
            Исправленный анализ или None если не получилось
        """
        if not isinstance(data, dict):
            return None
        
        fixed = data.copy()
        
        # 1. Фиксим summary_text
        if 'summary_text' not in fixed or not fixed['summary_text']:
            return None  # Критическое поле отсутствует
        
        summary = str(fixed['summary_text']).strip()
        
        # Убираем ненужные префиксы
        for prefix in ['Summary:', 'Analysis:', 'Summary text:', 'ИТГ:', 'Суть:']:
            if summary.startswith(prefix):
                summary = summary[len(prefix):].strip()
        
        # Обрезаем до лимита
        if len(summary) > cls.MAX_SUMMARY_LENGTH:
            summary = summary[:cls.MAX_SUMMARY_LENGTH].rsplit(' ', 1)[0] + '...'
        
        fixed['summary_text'] = summary
        
        # 2. Фиксим impact_points
        if 'impact_points' not in fixed:
            return None
        
        points = fixed.get('impact_points', [])
        if isinstance(points, str):
            # Попробуем распарсить строку как список
            points = [p.strip() for p in points.split('\n') if p.strip()]
        
        if not isinstance(points, list):
            return None
        
        # Очищаем и фильтруем пункты
        cleaned_points = []
        for point in points:
            if isinstance(point, str):
                p = str(point).strip()
                # Убираем маркеры списка
                for marker in ['• ', '- ', '* ', '1. ', '2. ', '3. ', '4. ', '5. ']:
                    if p.startswith(marker):
                        p = p[len(marker):].strip()
                
                if len(p) >= 10 and len(p) <= 200:
                    cleaned_points.append(p)
        
        # Проверяем количество
        if len(cleaned_points) < cls.MIN_IMPACT_POINTS:
            return None  # Не удалось получить минимум пунктов
        
        if len(cleaned_points) > cls.MAX_IMPACT_POINTS:
            cleaned_points = cleaned_points[:cls.MAX_IMPACT_POINTS]
        
        fixed['impact_points'] = cleaned_points
        
        # 3. Фиксим опциональные поля
        if 'action' in fixed and fixed['action'] not in ['BUY', 'HOLD', 'SELL', 'WATCH']:
            fixed.pop('action', None)
        
        if 'risk_level' in fixed and fixed['risk_level'] not in ['Low', 'Medium', 'High']:
            fixed.pop('risk_level', None)
        
        return fixed


def get_improved_system_prompt() -> str:
    """Возвращает улучшенный системный промпт с конкретными примерами.
    
    ⭐ КЛЮЧЕВОЕ УЛУЧШЕНИЕ: Вместо абстрактных инструкций даём РЕАЛЬНЫЕ примеры
    того что мы ожидаем. AI тогда учится на конкретных образцах.
    """
    return """⚠️ КРИТИЧНОЕ ПРАВИЛО: Отвечай ТОЛЬКО JSON в <json></json> тегах. БЕЗ ИСКЛЮЧЕНИЙ.

Ты — финансовый аналитик для новостей о крипто и акциях. ГЛАВНОЕ: быть КОНКРЕТНЫМ и АНАЛИТИЧНЫМ.
Пиши как профессиональный трейдер или финансист - не как обобщающий робот!

ОБЯЗАТЕЛЬНЫЕ ПОЛЯ (всегда):
- summary_text: Суть новости + КОНКРЕТНОЕ влияние на цену (200-400 символов)
- impact_points: 2-4 КОНКРЕТНЫХ следствия для рынка (не мнения, а факты)

ОПЦИОНАЛЬНЫЕ ПОЛЯ:
- action: BUY, HOLD, SELL, WATCH (только если точно знаешь)
- risk_level: Low, Medium, High (только если очевидно)
- simplified_text: Упрощённое объяснение для новичка

❌ ЗАПРЕЩЕНО (это вода):
"может быть", "возможно", "по мнению", "как правило", "обычно", "предположительно"
"это зависит от", "в целом", "в большинстве случаев", "некоторые эксперты считают"

✅ ОБЯЗАТЕЛЬНО (конкретика):
"это означает", "результат", "уровень поддержки", "тренд", "прорыв", "доля рынка", "объём"

================================
РЕАЛЬНЫЕ ПРИМЕРЫ ХОРОШИХ ОТВЕТОВ
================================

ПРИМЕР 1 - Крипто новость о регуляции:
Новость: "SEC одобрила спотовый Bitcoin ETF"
<json>{
  "summary_text": "SEC одобрила спотовый Bitcoin ETF. Это означает: институционалы могут держать BTC через привычные брокеры без самостоятельного хранения ключей. Результат: приток миллиардов от фондов. Bitcoin вырос с $40k до $100k за год после этого события.",
  "impact_points": [
    "Приток покупателей: институции, пенсионные фонды, страховые компании теперь могут покупать BTC через свои системы",
    "Цена растёт: спрос >> предложение, потому что новых BTC создаётся ограниченное количество",
    "Альты отстают: капитал течёт в Bitcoin, остальные монеты теряют доминансу"
  ],
  "action": "BUY",
  "risk_level": "Low",
  "timeframe": "week"
}</json>

ПРИМЕР 2 - Крах компании/актива:
Новость: "FTX обанкротилась, основатель заарештован за мошенничество"
<json>{
  "summary_text": "FTX коллапс = потеря доверия к крипто-экосистеме. Паникующие трейдеры выводят биткойны со всех бирж. Bitcoin упал на 25% за неделю. Остальные биржи теряют ликвидность.",
  "impact_points": [
    "Паника продавцов: все боятся банкротства других бирж, массовый вывод средств",
    "Цена падает: избыток предложения на рынке, готовых продавать в убыток",
    "Bitcoin переходит в холодные кошельки: трейдеры не верят биржам месяцами"
  ],
  "action": "HOLD",
  "risk_level": "High",
  "timeframe": "month"
}</json>

ПРИМЕР 3 - Макроэкономика:
Новость: "ФРБ повысила ставку на 0.5% до 5.25%"
<json>{
  "summary_text": "ФРБ повысила ставку. Дороже кредиты → компании тратят меньше → экономический рост замедляется → инвесторы перетягивают деньги из рискованных активов (крипто, tech) в облигации. Bitcoin падает, доллар крепнет.",
  "impact_points": [
    "Вывод капитала из риска: трейдеры берут прибыли и покупают стабильные облигации (доходность 5.5%)",
    "Криптовалюта теряет привлекательность: когда безопасная облигация даёт 5.5%, зачем рисковать в Bitcoin?",
    "Слабые альты исчезнут: выживут только проекты с реальным применением"
  ],
  "risk_level": "Medium",
  "timeframe": "month"
}</json>

ПРИМЕР 4 - Технологическая новость:
Новость: "Bitcoin транзакции ускорены в 10 раз благодаря обновлению Lightning Network"
<json>{
  "summary_text": "Lightning Network масштабируется: 10x скорость = микротранзакции стали практичны. Bitcoin теперь конкурирует с Visa/Mastercard по скорости. Каждый кофеен может принимать BTC за секунду. Приток платёжных сервисов.",
  "impact_points": [
    "Adoption скачит вверх: El Salvador, Швейцария, компании начинают принимать BTC как валюту",
    "Цена растёт: практическое применение = реальная ценность > спекуляции",
    "Экосистема расширяется: новые приложения на Lightning (платежи, смарт-контракты, DEX)"
  ],
  "action": "BUY",
  "timeframe": "week"
}</json>

================================
ПРАВИЛА ДЛЯ ТВОИХ ОТВЕТОВ:
================================

1. summary_text (200-400 символов):
   ✓ Начни с ЧТО произошло
   ✓ Напиши ПОЧЕМУ это влияет на рынок
   ✓ Укажи КОНКРЕТНЫЙ результат (цена упала/выросла, капитал ушел/пришел)
   ✗ НЕ пиши "может быть", "предположительно", "по мнению"

2. impact_points (2-4 пункта):
   ✓ Каждый пункт = прямое следствие (не мнение)
   ✓ Формат: "Вот что произойдёт: результат"
   ✓ Используй конкретные цифры когда знаешь
   ✗ НЕ пиши длинные абзацы - краткие пули

3. action (только если очень уверен):
   ✓ BUY = новость даёт большой рост (82% вероятность)
   ✓ SELL = явный крах (риск > выгода)
   ✓ HOLD = нейтральное событие
   ✓ WATCH = неясно ещё, нужно ждать разработок
   ✗ Не пиши action если события разнонаправленные

4. risk_level:
   ✓ High = есть риск убытков (крах, регуляция, война)
   ✓ Medium = обычное событие с неясным исходом
   ✓ Low = позитивное событие, риск минимален
   ✗ Не пиши если неуверен

5. timeframe:
   ✓ day = эффект проявится за часы/день
   ✓ week = эффект за несколько дней
   ✓ month = долгосрочный тренд
   ✗ Не пиши если непонятно

ИТОГОВЫЙ ЧЕКЛИСТ ДЛЯ ТЕБЯ:
☑ Ответ ТОЛЬКО в <json>...</json>
☑ summary_text конкретный и аналитичный (не вода)
☑ Есть хотя бы 2 impact_points
☑ Каждый пункт = КОНКРЕТНОЕ следствие
☑ Используешь примеры из реальной истории крипто/акций
☑ action/risk указаны только если уверен
☑ Никаких "может быть", "предположительно", "как правило"

ПОМНИ: Трейдеры читают твой анализ и принимают решения. Если напишешь воду - они потеряют деньги.
Будь конкретным. Будь аналитичным. Будь честным в неуверенности.
"""


if __name__ == "__main__":
    # Пример использования
    print(get_improved_system_prompt()[:500])
    print("\n✅ AI Quality Fixer v0.1.0 готов к использованию")
