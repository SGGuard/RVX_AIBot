"""
Передовая система адаптивного обучения (v0.21.0)
Включает: спиральное обучение, персонализацию, геймификацию, интерактивность
"""

from enum import Enum
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
import json

class LearningStyle(Enum):
    """Стили обучения (по Флемингу)"""
    VISUAL = "visual"      # Визуальное (диаграммы, видео)
    AUDITORY = "auditory"  # Аудиальное (слушание, обсуждение)
    READING = "reading"    # Чтение/письмо (текст, конспекты)
    KINESTHETIC = "kinesthetic"  # Кинестетическое (практика, опыт)


class DifficultyLevel(Enum):
    """Уровни сложности"""
    BEGINNER = 1
    ELEMENTARY = 2
    INTERMEDIATE = 3
    ADVANCED = 4
    EXPERT = 5


@dataclass
class UserLearningProfile:
    """Профиль обучения пользователя"""
    user_id: int
    current_level: DifficultyLevel
    learning_style: LearningStyle
    topics_covered: List[str]  # Пройденные темы
    knowledge_graph: Dict[str, float]  # {тема: прогресс 0-1}
    learning_pace: float  # 0.5 (медленный) до 2.0 (быстрый)
    preferred_length: str  # "short" (5 мин), "medium" (15 мин), "long" (30 мин)
    recent_scores: List[float]  # Последние оценки за квизы
    
    def get_recommended_topics(self) -> List[str]:
        """Рекомендованные следующие темы на основе прогресса"""
        # Рекомендуем 70% пройденных + 30% новых
        completed = [t for t, p in self.knowledge_graph.items() if p >= 0.7]
        incomplete = [t for t, p in self.knowledge_graph.items() if p < 0.7]
        
        return incomplete[:2] + completed[:1]  # 2 новых, 1 повторение
    
    def get_next_difficulty(self) -> DifficultyLevel:
        """Автоматическое повышение сложности"""
        if len(self.recent_scores) >= 3:
            avg_score = sum(self.recent_scores[-3:]) / 3
            if avg_score >= 0.85:
                if self.current_level.value < 5:
                    return DifficultyLevel(self.current_level.value + 1)
        return self.current_level


class SpiralLearning:
    """Спиральное обучение - повторение с углублением"""
    
    @staticmethod
    def get_spiral_sequence(topic: str, level: DifficultyLevel) -> List[Dict]:
        """Спиральная последовательность для темы
        
        1 витток: основные концепции
        2 виток: детали и примеры
        3 виток: практическое применение
        4 виток: критическое мышление
        """
        sequences = {
            "blockchain_basics": {
                DifficultyLevel.BEGINNER: [
                    {
                        "turn": 1,
                        "title": "Что такое блокчейн?",
                        "content": "Основные концепции: распределённая сеть, блоки, хэши",
                        "type": "theory"
                    },
                    {
                        "turn": 2,
                        "title": "Как работает блокчейн?",
                        "content": "Подробный процесс: создание блока, цепь, консенсус",
                        "type": "explanation"
                    }
                ],
                DifficultyLevel.INTERMEDIATE: [
                    {
                        "turn": 1,
                        "title": "Структура блоков",
                        "content": "Header, транзакции, Merkle tree",
                        "type": "deep_dive"
                    },
                    {
                        "turn": 2,
                        "title": "Алгоритмы консенсуса",
                        "content": "PoW, PoS, различия и применение",
                        "type": "comparison"
                    }
                ]
            }
        }
        
        return sequences.get(topic, {}).get(level, [])


class PersonalizedLearningPath:
    """Персонализированный путь обучения"""
    
    @staticmethod
    def create_path(profile: UserLearningProfile) -> List[Dict]:
        """Создаёт персональный путь на основе профиля"""
        path = []
        
        # Шаг 1: Диагностика пробелов
        weak_areas = [t for t, p in profile.knowledge_graph.items() if p < 0.5]
        
        # Шаг 2: Рекомендованные темы (рядом с пройденными)
        recommended = profile.get_recommended_topics()
        
        # Шаг 3: Адаптивная сложность
        next_level = profile.get_next_difficulty()
        
        # Собираем путь
        if weak_areas:
            path.append({
                "phase": "reinforcement",
                "topics": weak_areas[:1],
                "level": profile.current_level,
                "format": "interactive_quiz"
            })
        
        path.append({
            "phase": "progression",
            "topics": recommended,
            "level": next_level,
            "format": "spiral_learning"
        })
        
        path.append({
            "phase": "application",
            "topics": recommended[:1],
            "level": next_level,
            "format": "real_world_case"
        })
        
        return path


class Gamification:
    """Геймификация обучения"""
    
    # XP за разные действия
    XP_REWARDS = {
        "complete_lesson": 50,
        "perfect_quiz": 100,
        "daily_streak": 25,
        "help_other_user": 10,
        "reach_milestone": 200,
        "first_in_topic": 75
    }
    
    # Достижения
    ACHIEVEMENTS = {
        "first_step": {
            "title": "Первый шаг",
            "description": "Пройти первый урок",
            "icon": "🌱"
        },
        "knowledge_seeker": {
            "title": "Ищущий знаний",
            "description": "Пройти 5 уроков",
            "icon": "🔍"
        },
        "expert": {
            "title": "Эксперт",
            "description": "Достичь уровня Expert",
            "icon": "🏆"
        },
        "perfect_streak": {
            "title": "Идеальный результат",
            "description": "7 дней подряд 90%+ на тестах",
            "icon": "⚡"
        },
        "teacher": {
            "title": "Учитель",
            "description": "Помочь 10 другим пользователям",
            "icon": "👨‍🏫"
        }
    }
    
    @staticmethod
    def calculate_xp(action: str, score: float = 1.0) -> int:
        """Расчёт XP с бонусами за качество"""
        base_xp = Gamification.XP_REWARDS.get(action, 0)
        
        # Бонус за хороший результат (для quiz)
        if score > 0.9 and action == "perfect_quiz":
            base_xp = int(base_xp * 1.5)
        elif score < 0.7 and action == "perfect_quiz":
            base_xp = int(base_xp * 0.5)
        
        return base_xp
    
    @staticmethod
    def get_next_milestone(current_xp: int) -> Dict:
        """Следующий миллион (уровень)"""
        milestones = [
            {"xp": 100, "title": "Новичок", "icon": "🌱"},
            {"xp": 500, "title": "Любопытный", "icon": "🤔"},
            {"xp": 1500, "title": "Студент", "icon": "📚"},
            {"xp": 3500, "title": "Опытный", "icon": "🚀"},
            {"xp": 7000, "title": "Мастер", "icon": "⭐"},
            {"xp": 15000, "title": "Легенда", "icon": "👑"}
        ]
        
        next_milestone = next((m for m in milestones if m["xp"] > current_xp), milestones[-1])
        return next_milestone


class InteractiveLearning:
    """Интерактивные форматы обучения"""
    
    FORMATS = {
        "quiz": {
            "description": "Классический тест",
            "time": 10,
            "questions": 5
        },
        "flashcard": {
            "description": "Карточки для запоминания",
            "time": 5,
            "questions": 10
        },
        "scenario": {
            "description": "Ситуационная задача",
            "time": 15,
            "questions": 1
        },
        "code_challenge": {
            "description": "Кодовый вызов",
            "time": 20,
            "questions": 1
        },
        "discussion": {
            "description": "Обсуждение с ИИ",
            "time": 10,
            "questions": 3
        },
        "peer_review": {
            "description": "Рецензирование коллег",
            "time": 15,
            "questions": 1
        }
    }
    
    @staticmethod
    def get_best_format(learning_style: LearningStyle, topic: str) -> str:
        """Рекомендованный формат для стиля обучения"""
        recommendations = {
            LearningStyle.VISUAL: "flashcard",
            LearningStyle.AUDITORY: "discussion",
            LearningStyle.READING: "quiz",
            LearningStyle.KINESTHETIC: "code_challenge"
        }
        return recommendations.get(learning_style, "quiz")


class AdaptiveContent:
    """Адаптивный контент на основе стиля и уровня"""
    
    @staticmethod
    def generate_content(
        topic: str,
        learning_style: LearningStyle,
        level: DifficultyLevel
    ) -> Dict:
        """Генерирует контент, подходящий для стиля и уровня"""
        
        content_templates = {
            "visual": {
                "BEGINNER": "Диаграмма с пояснениями",
                "INTERMEDIATE": "Интерактивная диаграмма",
                "EXPERT": "Сравнительная визуализация"
            },
            "auditory": {
                "BEGINNER": "Объяснение простыми словами",
                "INTERMEDIATE": "Дискуссия с примерами",
                "EXPERT": "Дебаты по концепциям"
            },
            "reading": {
                "BEGINNER": "Простой текст с примерами",
                "INTERMEDIATE": "Статья с деталями",
                "EXPERT": "Исследовательская работа"
            },
            "kinesthetic": {
                "BEGINNER": "Простое упражнение",
                "INTERMEDIATE": "Практический проект",
                "EXPERT": "Реальный кейс"
            }
        }
        
        style = learning_style.name.lower()
        level_name = level.name
        
        return {
            "content_type": content_templates.get(style, {}).get(level_name, "quiz"),
            "difficulty": level,
            "estimated_time": 10 + (level.value * 5),
            "interaction_level": "high" if level.value >= 3 else "medium"
        }


class FeedbackSystem:
    """Интеллектуальная система обратной связи"""
    
    @staticmethod
    def generate_feedback(
        user_answer: str,
        correct_answer: str,
        level: DifficultyLevel
    ) -> Dict:
        """Генерирует конструктивную обратную связь"""
        
        if user_answer == correct_answer:
            feedbacks = [
                "Отлично! ✨ Ты полностью понимаешь эту концепцию.",
                "Верно! 🎯 Это классный пример глубокого понимания.",
                "Супер! 🚀 Продвигайся дальше, ты на правильном пути."
            ]
            return {
                "status": "correct",
                "message": feedbacks[hash(user_answer) % len(feedbacks)],
                "next_action": "proceed_to_next",
                "xp_earned": Gamification.calculate_xp("perfect_quiz", 1.0)
            }
        else:
            # Конструктивная критика на основе уровня
            if level.value <= 2:  # Для новичков - поддержка
                message = f"Хороший подход, но правильный ответ: {correct_answer}. Это касается..."
            else:  # Для опытных - анализ
                message = f"Интересно, почему ты выбрал это? Правильно: {correct_answer}. Различие в..."
            
            return {
                "status": "incorrect",
                "message": message,
                "explanation": "Помощь от системы",
                "next_action": "retry_or_skip",
                "xp_earned": Gamification.calculate_xp("perfect_quiz", 0.3)
            }


class MicroLearning:
    """Микрообучение - короткие сессии 5-10 минут"""
    
    @staticmethod
    def create_micro_lesson(topic: str, duration: int = 5) -> Dict:
        """Создаёт короткий урок (5-10 минут)"""
        
        return {
            "type": "micro_lesson",
            "duration_minutes": duration,
            "format": "key_points_only",
            "structure": [
                {
                    "part": "hook",
                    "duration": 1,
                    "content": "Интересный вопрос или кейс"
                },
                {
                    "part": "main",
                    "duration": 3,
                    "content": "Только самое важное"
                },
                {
                    "part": "action",
                    "duration": 1,
                    "content": "Что делать с этим знанием"
                }
            ],
            "reinforcement": "Повторение завтра через спиральный метод"
        }


class CollaborativeLearning:
    """Совместное обучение - пиры помогают друг другу"""
    
    @staticmethod
    def match_study_buddy(user_id: int, topic: str) -> Optional[int]:
        """Находит напарника для совместного изучения"""
        # В реальной системе ищет пользователя:
        # - На похожем уровне (+/- 1 уровень)
        # - Изучающего ту же тему
        # - С противоположным стилем обучения (для разнообразия)
        return None  # Placeholder
    
    @staticmethod
    def create_discussion_prompt(topic: str) -> str:
        """Создаёт вопрос для обсуждения с напарником"""
        questions = {
            "blockchain_basics": "Как бы ты объяснил блокчейн своему другу, который ничего не знает о технологиях?",
            "bitcoin": "Какие возможные проблемы может решить Bitcoin?",
            "cryptography": "Почему криптография важна в блокчейне?"
        }
        return questions.get(topic, "Что самое интересное ты узнал в этой теме?")


# Интеграция с системой
def initialize_learning_profile(user_id: int) -> UserLearningProfile:
    """Создаёт профиль обучения для нового пользователя"""
    return UserLearningProfile(
        user_id=user_id,
        current_level=DifficultyLevel.BEGINNER,
        learning_style=LearningStyle.VISUAL,  # Определяется через диагностику
        topics_covered=[],
        knowledge_graph={},
        learning_pace=1.0,
        preferred_length="medium",
        recent_scores=[]
    )


def get_recommended_learning_session(profile: UserLearningProfile) -> Dict:
    """Возвращает рекомендованную сессию обучения"""
    
    # Выбираем лучший формат для стиля
    best_format = InteractiveLearning.get_best_format(
        profile.learning_style,
        profile.get_recommended_topics()[0] if profile.get_recommended_topics() else "blockchain_basics"
    )
    
    # Получаем контент
    content = AdaptiveContent.generate_content(
        topic=profile.get_recommended_topics()[0] if profile.get_recommended_topics() else "blockchain_basics",
        learning_style=profile.learning_style,
        level=profile.current_level
    )
    
    # Путь обучения
    path = PersonalizedLearningPath.create_path(profile)
    
    return {
        "recommended_format": best_format,
        "content": content,
        "learning_path": path,
        "next_milestone": Gamification.get_next_milestone(500),  # Placeholder XP
        "estimated_session_time": 15,
        "personalization_level": "High"
    }
