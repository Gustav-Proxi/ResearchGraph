from research_graph.service import ResearchGraphService


def test_model_dashboard_has_provider_catalog():
    service = ResearchGraphService()

    dashboard = service.model_dashboard()

    assert dashboard["catalog"]["providers"]
    assert dashboard["catalog"]["local_model_presets"]
    assert dashboard["catalog"]["embedding_presets"]


def test_can_update_model_settings_and_add_custom_model():
    service = ResearchGraphService()

    updated = service.update_model_settings(
        {
            "primary_provider": "ollama",
            "primary_model": "llama3.2:1b",
            "embedding_provider": "ollama",
            "embedding_model": "nomic-embed-text",
        }
    )
    custom = service.add_custom_model(
        {
            "provider": "custom-openai-compatible",
            "name": "Lab Endpoint",
            "model": "lab-model",
            "model_type": "chat",
        }
    )

    assert updated["primary_provider"] == "ollama"
    assert updated["primary_model"] == "llama3.2:1b"
    assert custom["name"] == "Lab Endpoint"
    assert any(item["name"] == "Lab Endpoint" for item in service.model_settings()["custom_models"])
