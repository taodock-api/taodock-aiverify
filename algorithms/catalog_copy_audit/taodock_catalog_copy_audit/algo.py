"""Adapter for the AI Verify test-engine algorithm interface."""

import json
from pathlib import Path

from aiverify_test_engine.interfaces.ialgorithm import IAlgorithm
from aiverify_test_engine.plugins.enums.plugin_type import PluginType
from aiverify_test_engine.plugins.metadata.plugin_metadata import PluginMetadata

from .audit import COLUMNS, audit_rows


class CatalogCopyAudit(IAlgorithm):
    def __init__(
        self,
        data_serializer,
        model_serializer,
        ground_truth_serializer,
        initial_data_instance=None,
        initial_model_instance=None,
        **kwargs,
    ):
        self.dataset = (
            initial_data_instance
            if initial_data_instance is not None
            else data_serializer[0]
        )
        self.report_progress = kwargs.get("progress_callback")
        self.progress = 0
        self.results = {}

    @staticmethod
    def get_metadata():
        with (
            Path(__file__).with_name("algo.meta.json").open(encoding="utf-8") as stream
        ):
            meta = json.load(stream)
        return PluginMetadata(
            name=meta["name"], description=meta["description"], version=meta["version"]
        )

    @staticmethod
    def get_plugin_type():
        return PluginType.ALGORITHM

    def setup(self):
        self.progress = 0
        self.results = {}

    def get_progress(self):
        return self.progress

    def get_results(self):
        return self.results

    def generate(self):
        self.setup()
        dataset = self.dataset.get_data()
        if len(dataset.columns) != len(COLUMNS) or set(dataset.columns) != COLUMNS:
            raise ValueError(
                "Dataset must contain sku, measurements, required_phrases, and draft"
            )
        self.results = audit_rows(dataset.fillna("").to_dict(orient="records"))
        self.progress = 100
        if self.report_progress:
            self.report_progress(self.progress)
