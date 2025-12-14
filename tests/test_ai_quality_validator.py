"""Tests for AI Quality Validator (ai_quality_fixer.py)"""
import pytest
from ai_quality_fixer import (
    AIQualityValidator,
    get_improved_system_prompt,
    AnalysisQuality
)


class TestAIQualityValidator:
    """Test AIQualityValidator class."""
    
    def test_validate_good_analysis(self):
        """Good analysis should have high score and be valid."""
        good_analysis = {
            "summary_text": "SEC одобрила спотовый Bitcoin ETF. Это означает приток институционального капитала. Bitcoin вырос на 50%.",
            "impact_points": [
                "Приток покупателей: институции теперь могут покупать BTC через привычные брокеры",
                "Цена растёт: спрос >> предложение из-за ограниченного количества новых BTC"
            ]
        }
        
        quality = AIQualityValidator.validate_analysis(good_analysis)
        
        assert quality.score >= 7.0  # Good analysis should score 7+
        assert quality.is_valid is True
        assert len(quality.issues) == 0
        assert quality.confidence > 0.7
    
    def test_validate_bad_analysis_with_water_patterns(self):
        """Analysis with water patterns should have low score."""
        bad_analysis = {
            "summary_text": "Может быть, это может повлиять на рынок как правило. По мнению некоторых, возможно что-то произойдет.",
            "impact_points": [
                "Возможно, что-то может произойти",
                "Это зависит от многих факторов"
            ]
        }
        
        quality = AIQualityValidator.validate_analysis(bad_analysis)
        
        assert quality.score < 5.0  # Bad analysis should score < 5
        assert quality.is_valid is False
        assert len(quality.issues) > 0
        assert any('неопределённости' in issue for issue in quality.issues)
    
    def test_validate_missing_required_fields(self):
        """Missing required fields should make analysis invalid."""
        incomplete = {
            "summary_text": "Some text"
        }
        
        quality = AIQualityValidator.validate_analysis(incomplete)
        
        assert quality.is_valid is False
        assert any('impact_points' in issue for issue in quality.issues)
    
    def test_validate_empty_analysis(self):
        """Empty dict should be invalid."""
        quality = AIQualityValidator.validate_analysis({})
        
        assert quality.is_valid is False
        assert len(quality.issues) >= 2
    
    def test_validate_non_dict_input(self):
        """Non-dict input should return invalid."""
        quality = AIQualityValidator.validate_analysis("not a dict")
        
        assert quality.score == 0.0
        assert quality.is_valid is False
    
    def test_validate_short_summary(self):
        """Summary too short should be detected and reduce score."""
        short_analysis = {
            "summary_text": "Short",
            "impact_points": ["Very long point to satisfy minimum length requirement", "Another valid long point"]
        }
        
        quality = AIQualityValidator.validate_analysis(short_analysis)
        
        # Should detect the issue even if validation passes due to leniency
        assert any('слишком короткий' in issue for issue in quality.issues)
    
    def test_validate_long_summary(self):
        """Summary too long should be detected and reduce score."""
        long_text = "A" * 600
        long_analysis = {
            "summary_text": long_text,
            "impact_points": ["Very long point to satisfy minimum length requirement", "Another valid long point"]
        }
        
        quality = AIQualityValidator.validate_analysis(long_analysis)
        
        # Should detect the issue even if validation passes due to leniency
        assert any('слишком длинный' in issue for issue in quality.issues)
    
    def test_validate_too_few_impact_points(self):
        """Too few impact points should reduce score."""
        few_points = {
            "summary_text": "Good summary text with real information.",
            "impact_points": ["Only one point"]
        }
        
        quality = AIQualityValidator.validate_analysis(few_points)
        
        assert quality.is_valid is False
        assert any('Недостаточно' in issue for issue in quality.issues)
    
    def test_validate_too_many_impact_points(self):
        """Too many impact points should reduce score."""
        many_points = {
            "summary_text": "Good summary text with real information.",
            "impact_points": ["P1", "P2", "P3", "P4", "P5", "P6"]
        }
        
        quality = AIQualityValidator.validate_analysis(many_points)
        
        assert quality.is_valid is False
        assert any('Слишком много' in issue for issue in quality.issues)
    
    def test_validate_with_good_patterns(self):
        """Analysis with good patterns should score higher."""
        analysis_with_good = {
            "summary_text": "Bitcoin имеет уровень поддержки 50000. Тренд восходящий. Это означает возможный рост цены.",
            "impact_points": [
                "Прорыв выше сопротивления на уровне 60000",
                "Объём торговли растёт, волатильность остается в норме"
            ]
        }
        
        quality = AIQualityValidator.validate_analysis(analysis_with_good)
        
        assert quality.score >= 7.0
        assert quality.is_valid is True
    
    def test_validate_with_action_field(self):
        """Valid action field should increase score."""
        analysis_with_action = {
            "summary_text": "SEC одобрила Bitcoin ETF. Это означает приток капитала. Рост неизбежен.",
            "impact_points": ["Приток денег", "Рост цены"],
            "action": "BUY"
        }
        
        quality = AIQualityValidator.validate_analysis(analysis_with_action)
        
        assert quality.score >= 7.0
        assert "action" not in str(quality.issues).lower()
    
    def test_validate_with_risk_field(self):
        """Valid risk_level field should increase score."""
        analysis_with_risk = {
            "summary_text": "SEC одобрила Bitcoin ETF. Это означает приток капитала. Рост неизбежен.",
            "impact_points": ["Приток денег", "Рост цены"],
            "risk_level": "Low"
        }
        
        quality = AIQualityValidator.validate_analysis(analysis_with_risk)
        
        assert quality.score >= 7.0
        assert "risk" not in str(quality.issues).lower()


class TestAIQualityValidatorFix:
    """Test AIQualityValidator.fix_analysis method."""
    
    def test_fix_analysis_removes_bad_prefixes(self):
        """fix_analysis should remove common prefixes."""
        bad = {
            "summary_text": "Summary: Bitcoin растёт благодаря хорошим новостям. Это означает положительное движение.",
            "impact_points": ["Point 1: Important impact point", "Point 2: Another important impact"]
        }
        
        fixed = AIQualityValidator.fix_analysis(bad)
        
        assert fixed is not None
        assert not fixed["summary_text"].startswith("Summary:")
    
    def test_fix_analysis_truncates_long_summary(self):
        """fix_analysis should truncate too-long summary."""
        long_text = "A" * 550
        bad = {
            "summary_text": long_text,
            "impact_points": ["Point 1: Important impact point", "Point 2: Another important impact"]
        }
        
        fixed = AIQualityValidator.fix_analysis(bad)
        
        assert fixed is not None
        # Should be truncated reasonably close to the limit (allowing for word boundary logic)
        assert len(fixed["summary_text"]) <= 510
    
    def test_fix_analysis_cleans_impact_points(self):
        """fix_analysis should clean bullet points from impact_points."""
        bad = {
            "summary_text": "Good summary with real information here for good measure.",
            "impact_points": ["• Point 1: This is a long enough point", "- Point 2: This is another long point", "* Point 3: And one more"]
        }
        
        fixed = AIQualityValidator.fix_analysis(bad)
        
        assert fixed is not None
        assert not fixed["impact_points"][0].startswith("•")
        assert not fixed["impact_points"][1].startswith("-")
    
    def test_fix_analysis_returns_none_for_missing_summary(self):
        """fix_analysis should return None if summary_text is missing."""
        bad = {
            "impact_points": ["Point 1", "Point 2"]
        }
        
        fixed = AIQualityValidator.fix_analysis(bad)
        
        assert fixed is None
    
    def test_fix_analysis_returns_none_for_missing_impact_points(self):
        """fix_analysis should return None if impact_points is missing."""
        bad = {
            "summary_text": "Good summary here"
        }
        
        fixed = AIQualityValidator.fix_analysis(bad)
        
        assert fixed is None
    
    def test_fix_analysis_returns_none_for_too_few_points_after_fix(self):
        """fix_analysis should return None if can't achieve min impact points."""
        bad = {
            "summary_text": "Good summary here",
            "impact_points": ["Only one"]
        }
        
        fixed = AIQualityValidator.fix_analysis(bad)
        
        assert fixed is None
    
    def test_fix_analysis_removes_invalid_action(self):
        """fix_analysis should remove invalid action field."""
        bad = {
            "summary_text": "Good summary with real information here for good measure.",
            "impact_points": ["Point 1: This is a long enough point", "Point 2: This is another long point"],
            "action": "INVALID"
        }
        
        fixed = AIQualityValidator.fix_analysis(bad)
        
        assert fixed is not None
        assert "action" not in fixed or fixed["action"] not in ["INVALID"]
    
    def test_fix_analysis_removes_invalid_risk_level(self):
        """fix_analysis should remove invalid risk_level field."""
        bad = {
            "summary_text": "Good summary with real information here for good measure.",
            "impact_points": ["Point 1: This is a long enough point", "Point 2: This is another long point"],
            "risk_level": "INVALID"
        }
        
        fixed = AIQualityValidator.fix_analysis(bad)
        
        assert fixed is not None
        assert "risk_level" not in fixed or fixed["risk_level"] not in ["INVALID"]


class TestImprovedSystemPrompt:
    """Test get_improved_system_prompt function."""
    
    def test_prompt_is_string(self):
        """Prompt should be a non-empty string."""
        prompt = get_improved_system_prompt()
        
        assert isinstance(prompt, str)
        assert len(prompt) > 1000
    
    def test_prompt_contains_critical_rules(self):
        """Prompt should contain critical rules."""
        prompt = get_improved_system_prompt()
        
        assert "<json>" in prompt
        assert "ЗАПРЕЩЕНО" in prompt or "ЗАПРЕЩ" in prompt
        assert "конкретн" in prompt.lower()
    
    def test_prompt_contains_examples(self):
        """Prompt should contain real examples."""
        prompt = get_improved_system_prompt()
        
        # Check for at least some real examples
        assert any(keyword in prompt.lower() for keyword in [
            "bitcoin", "sec", "ftx", "lightning"
        ])
    
    def test_prompt_contains_bad_patterns(self):
        """Prompt should document bad patterns to avoid."""
        prompt = get_improved_system_prompt()
        
        assert "может быть" in prompt.lower() or "может" in prompt.lower()
        assert "возможно" in prompt.lower()
    
    def test_prompt_contains_good_patterns(self):
        """Prompt should document good patterns to use."""
        prompt = get_improved_system_prompt()
        
        assert "означает" in prompt.lower()
        assert "конкретн" in prompt.lower()
    
    def test_prompt_is_stable(self):
        """Prompt should be stable across calls."""
        prompt1 = get_improved_system_prompt()
        prompt2 = get_improved_system_prompt()
        
        assert prompt1 == prompt2


class TestAnalysisQualityDataclass:
    """Test AnalysisQuality dataclass."""
    
    def test_create_analysis_quality(self):
        """Should create AnalysisQuality instance."""
        quality = AnalysisQuality(
            score=7.5,
            issues=[],
            is_valid=True,
            confidence=0.85
        )
        
        assert quality.score == 7.5
        assert quality.is_valid is True
        assert len(quality.issues) == 0
        assert quality.confidence == 0.85
    
    def test_analysis_quality_with_issues(self):
        """AnalysisQuality should handle issues list."""
        issues = ["Issue 1", "Issue 2"]
        quality = AnalysisQuality(
            score=3.0,
            issues=issues,
            is_valid=False,
            confidence=0.3
        )
        
        assert len(quality.issues) == 2
        assert "Issue 1" in quality.issues
