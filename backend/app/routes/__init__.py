API_PREFIX = "/api/v1"


def register_blueprints(app):
    from app.routes.health import health_bp
    from app.routes.auth import auth_bp
    from app.routes.organisations import organisations_bp
    from app.routes.roles import roles_bp
    from app.routes.projects import projects_bp
    from app.routes.data_sources import project_sources_bp, sources_bp
    from app.routes.datasets import project_datasets_bp, datasets_bp
    from app.routes.reviews import project_reviews_bp, reviews_bp
    from app.routes.analysis import analysis_bp
    from app.routes.recommendations import project_recommendations_bp, recommendations_bp
    from app.routes.ai_summaries import project_summaries_bp, summaries_bp
    from app.routes.alerts import project_alerts_bp, alerts_bp
    from app.routes.reports import project_reports_bp, reports_bp
    from app.routes.workflows import project_workflows_bp, workflows_bp
    from app.routes.llm import llm_bp
    from app.routes.project_website import project_website_bp

    app.register_blueprint(health_bp, url_prefix=API_PREFIX)
    app.register_blueprint(auth_bp, url_prefix=f"{API_PREFIX}/auth")
    app.register_blueprint(organisations_bp, url_prefix=f"{API_PREFIX}/organisations")
    app.register_blueprint(roles_bp, url_prefix=f"{API_PREFIX}/organisations/<organisation_id>/roles")
    app.register_blueprint(projects_bp, url_prefix=f"{API_PREFIX}/projects")

    app.register_blueprint(project_sources_bp, url_prefix=f"{API_PREFIX}/projects/<project_id>/sources")
    app.register_blueprint(sources_bp, url_prefix=f"{API_PREFIX}/sources")

    app.register_blueprint(project_datasets_bp, url_prefix=f"{API_PREFIX}/projects/<project_id>/datasets")
    app.register_blueprint(datasets_bp, url_prefix=f"{API_PREFIX}/datasets")

    app.register_blueprint(project_reviews_bp, url_prefix=f"{API_PREFIX}/projects/<project_id>/reviews")
    app.register_blueprint(reviews_bp, url_prefix=f"{API_PREFIX}/reviews")

    app.register_blueprint(analysis_bp, url_prefix=f"{API_PREFIX}/projects/<project_id>/analysis")

    app.register_blueprint(
        project_recommendations_bp, url_prefix=f"{API_PREFIX}/projects/<project_id>/recommendations"
    )
    app.register_blueprint(recommendations_bp, url_prefix=f"{API_PREFIX}/recommendations")

    app.register_blueprint(project_summaries_bp, url_prefix=f"{API_PREFIX}/projects/<project_id>/ai-summaries")
    app.register_blueprint(summaries_bp, url_prefix=f"{API_PREFIX}/ai-summaries")

    app.register_blueprint(project_alerts_bp, url_prefix=f"{API_PREFIX}/projects/<project_id>/alerts")
    app.register_blueprint(alerts_bp, url_prefix=f"{API_PREFIX}/alerts")

    app.register_blueprint(project_reports_bp, url_prefix=f"{API_PREFIX}/projects/<project_id>/reports")
    app.register_blueprint(reports_bp, url_prefix=f"{API_PREFIX}/reports")

    app.register_blueprint(project_workflows_bp, url_prefix=f"{API_PREFIX}/projects/<project_id>/workflows")
    app.register_blueprint(workflows_bp, url_prefix=f"{API_PREFIX}/workflows")
    app.register_blueprint(llm_bp, url_prefix=f"{API_PREFIX}/llm")
    app.register_blueprint(
        project_website_bp, url_prefix=f"{API_PREFIX}/projects/<project_id>/website"
    )

    from app.routes.dataset_profile import datasets_profile_bp
    from app.routes.evaluation import evaluation_bp
    from app.routes.aspect_vocabulary import project_aspect_vocab_bp

    app.register_blueprint(datasets_profile_bp, url_prefix=f"{API_PREFIX}/datasets")
    app.register_blueprint(evaluation_bp, url_prefix=f"{API_PREFIX}/evaluation")
    app.register_blueprint(project_aspect_vocab_bp, url_prefix=f"{API_PREFIX}/projects/<project_id>/aspect-vocabulary")
