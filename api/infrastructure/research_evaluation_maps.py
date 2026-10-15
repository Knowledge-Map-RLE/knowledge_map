"""Явно подготовленная локальная цель оценщика; никогда не участвует в источниках обучения."""
from domain.article_maps import require, ArticleMapAccessDenied


class PreparedEvaluationMaps:
    def __init__(self, repository, bundle, owner):
        require(set(bundle) == {"map", "registry", "annotation", "origin"}, "Evaluation bundle fields differ")
        self.repository, self.bundle, self.owner = repository, bundle, owner

    def authorize(self, article, user):
        if article != self.bundle["map"]["article_id"]:
            return self.repository.authorize(article, user)
        if user != self.owner: raise ArticleMapAccessDenied("Prepared evaluation belongs to another owner")

    def get(self, article, pipeline, user, run):
        self.authorize(article, user)
        result = self.bundle["map"]
        if article == result["article_id"]:
            require(pipeline == "text_reified" and run == result["run_id"], "Prepared evaluation run differs")
            return result
        return self.repository.get(article, pipeline, user, run)
