"""AI Data Agent engine for the Data Pilot: memory, RAG grounding, and LLM streaming.

Extracted from src/pages/data_pilot.py so the agent logic is a reusable service
and the page only handles rendering and actions.
"""

from __future__ import annotations

import os
import re
from typing import Dict, List

import pandas as pd
import streamlit as st
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from src.config.constants import DATA_DIR
from src.config.settings import load_secrets_schema
from src.processing.forecasting import PredictiveIntelligence
from src.services.llm.manager import init_llm_controller
from src.services.pathao.status import get_pathao_order_status
from src.utils.ml_brain import NeuralBrain


def get_cached_brain():
    return NeuralBrain()


def _get_cached_forecast(df: pd.DataFrame):
    if (
        df is None
        or df.empty
        or "Date" not in df.columns
        or "Total Amount" not in df.columns
    ):
        return None
    df_daily = df.copy()
    df_daily["Day"] = pd.to_datetime(df_daily["Date"], errors="coerce").dt.date
    series = df_daily.groupby("Day")["Total Amount"].sum()
    if len(series) >= 3:
        forecasts, _ = PredictiveIntelligence.forecast(series)
        return forecasts
    return None


def _get_cached_anomalies(df: pd.DataFrame):
    if df is None or df.empty:
        return pd.DataFrame()
    return get_cached_brain().detect_anomalies(df)


class AgenticMemory:
    """Structured Key-Value memory for the AI Agent."""

    def __init__(self, filepath=None):
        if filepath is None:
            filepath = os.path.join(DATA_DIR, "pilot_memory.json")
        self.filepath = filepath
        self.memory = self._load()

    def _load(self) -> Dict[str, str]:
        if os.path.exists(self.filepath):
            try:
                import json

                with open(self.filepath, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (OSError, ValueError):
                return {}
        return {}

    def save(self):
        import json

        os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
        with open(self.filepath, "w", encoding="utf-8") as f:
            json.dump(self.memory, f, indent=4)

    def set_memory(self, key: str, value: str):
        self.memory[key] = value
        self.save()

    def delete_memory(self, key: str):
        if key in self.memory:
            del self.memory[key]
            self.save()

    def get_formatted_knowledge(self) -> str:
        if not self.memory:
            return ""
        lines = [f"  * {k.upper()}: {v}" for k, v in self.memory.items()]
        return "KNOWLEDGE_TYPE: Learned Operational Rules\n" + "\n".join(lines)


class AIDataAgent:
    """
    Enhanced AI-BI Agent with NLP Intent Routing & ML Grounding.
    Uses NeuralBrain for intent detection and PredictiveIntelligence for forecasting.
    """

    def __init__(
        self,
        provider="🛡️ Smart Failover (Free Tiers)",
        api_key=None,
        model_name=None,
        context_dfs: Dict[str, pd.DataFrame] = None,
    ):
        self.provider = provider
        self.api_key = api_key
        self.model_name = model_name
        self.controller = init_llm_controller()
        self.brain = get_cached_brain()
        self.agent_memory = AgenticMemory()
        if context_dfs is not None:
            self.context_dfs = context_dfs
        else:
            # Fallback to session state for interactive use
            self.context_dfs = {
                "sales": st.session_state.get("wc_curr_df"),
                "inventory_distribution": st.session_state.get("inv_res_data"),
                "stock_levels": st.session_state.get("wc_stock_df"),
                "pathao_dispatch": st.session_state.get("pathao_res_df"),
                "pathao_tracking": st.session_state.get("pilot_pathao_tracking_df"),
                "uploaded": st.session_state.get("pilot_uploaded_df"),
            }
        self.app_knowledge = self._load_app_knowledge()
        self.vectorizer = TfidfVectorizer(stop_words="english", lowercase=True)

    def _load_app_knowledge(self) -> List[str]:
        """Loads project blueprints, source code logic, and API schemas into the knowledge base."""
        knowledge = []
        # 1. Core Documentation & Blueprints
        docs = [
            "agent.md",
            "README.md",
            "data_pilot.md",
            "DEAD_CODE_REPORT.md",
            "ERROR_HANDLING_GUIDE.md",
            "DEVELOPMENT.md",
        ]
        for doc in docs:
            if os.path.exists(doc):
                try:
                    with open(doc, "r", encoding="utf-8") as f:
                        knowledge.append(
                            f"KNOWLEDGE_TYPE: Documentation | FILE: {doc}\n{f.read()[:4000]}"
                        )
                except OSError:
                    pass

        # 1.1 Persistent User-Taught Rules (Memory)
        mem_str = self.agent_memory.get_formatted_knowledge()
        if mem_str:
            knowledge.append(mem_str)

        # 2. REST API Schema & Contracts (Answers 'rest api data' context)
        try:
            schema = load_secrets_schema()
            if schema:
                knowledge.append(
                    f"KNOWLEDGE_TYPE: REST API Definition & Secrets Schema\n{str(schema)}"
                )
        except Exception:
            pass

        # 3. Source Code Logic (Sampling key orchestration files)
        src_samples = [
            "src/config/constants.py",
            "src/config/settings.py",
            "src/processing/data_processing.py",
            "src/services/woocommerce/client.py",
            "src/services/pathao/client.py",
            "src/services/llm/manager.py",
            "app.py",
        ]
        for src in src_samples:
            if os.path.exists(src):
                try:
                    with open(src, "r", encoding="utf-8") as f:
                        knowledge.append(
                            f"KNOWLEDGE_TYPE: Source Code Architecture | FILE: {src}\n{f.read()[:3000]}"
                        )
                except OSError:
                    pass
        return knowledge

    def _get_vector_context(self, query: str, top_k: int = 20) -> str:
        """
        Performs RAG retrieval by vectorizing dataframe rows and app-level knowledge,
        finding the most semantically relevant items to the query.
        """
        documents = []

        # 1. Include static App Knowledge (Docs/Source/API Schema)
        documents.extend(self.app_knowledge)

        # 2. Flatten DataFrames into searchable text documents
        for name, df in self.context_dfs.items():
            if df is not None and not df.empty:
                # Limit RAG context size for performance; focus on most recent if possible
                working_df = df.tail(500) if len(df) > 500 else df

                # Optimized Vectorized String Construction (10x+ faster than iterrows)
                str_df = working_df.astype(str).replace("nan", "")
                text_series = pd.Series(
                    [f"Source: {name} | "] * len(str_df), index=str_df.index
                )

                for col in str_df.columns:
                    text_series += f"{col}: " + str_df[col] + " | "
                documents.extend(text_series.tolist())

        if not documents:
            return ""

        try:
            # 2. Vectorize the knowledge base
            tfidf_matrix = self.vectorizer.fit_transform(documents)

            # 3. Vectorize the query
            query_vec = self.vectorizer.transform([query])

            # 4. Compute Similarity
            cosine_sim = cosine_similarity(query_vec, tfidf_matrix).flatten()

            # 5. Retrieve top K matches
            related_indices = cosine_sim.argsort()[-top_k:][::-1]

            relevant_chunks = []
            for idx in related_indices:
                if cosine_sim[idx] > 0.05:  # Threshold to filter out irrelevant noise
                    relevant_chunks.append(documents[idx])

            if relevant_chunks:
                return "\nRELEVANT DATA RECORDS FOUND:\n" + "\n".join(relevant_chunks)
            return ""
        except Exception as e:
            return f"\n(RAG Retrieval Error: {str(e)})\n"

    def get_grounded_insights(self, query: str) -> str:
        intent = self.brain.semantic_query_intent(query)
        insights = []

        if (
            intent["type"] == "ml_forecast"
            or "forecast" in query.lower()
            or "predict" in query.lower()
        ):
            df = self.context_dfs["sales"]
            forecasts = _get_cached_forecast(df)
            if forecasts:
                best = forecasts[0]
                insights.append(
                    f"ML FORECAST: '{best['name']}' predicts next 7 days will total approx ৳{sum(best['forecast']):,.0f}."
                )

        if (
            intent["type"] == "ml_anomaly"
            or "anomaly" in query.lower()
            or "unusual" in query.lower()
        ):
            df = self.context_dfs["sales"]
            anomalies = _get_cached_anomalies(df)
            if not anomalies.empty:
                top = anomalies.iloc[0]
                insights.append(
                    f"ML ANOMALY: A '{top['type']}' spike was detected on {top['date']} with value ৳{top['value']:,.0f} (Z-Score: {top['score']:.2f})."
                )

        # Pathao Live Tracking Intent (Regex extraction for Consignment IDs)
        pathao_match = re.search(r"(?i)(?:DD|D-|M-)\w+", query)
        if pathao_match:
            consignment_id = pathao_match.group(0).upper().strip()
            status_res = get_pathao_order_status(consignment_id)
            if "error" not in status_res:
                data = status_res.get("data", {})
                live_status = data.get("order_status", "Unknown")
                insights.append(
                    f"PATHAO LIVE STATUS: Consignment {consignment_id} is currently '{live_status}'. Payment status: {data.get('payment_status')}."
                )

        # Report Generation Intent
        if "report" in query.lower() or "summary" in query.lower():
            insights.append(
                "ACTION: The user is requesting a comprehensive report or summary. Please format the response as a detailed, structured markdown report covering sales, inventory, and fulfillment performance based on the available data context."
            )

        # RAG Retrieval: Vectorized context injection
        rag_context = self._get_vector_context(query)
        if rag_context:
            insights.append(rag_context)

        # General grounding
        for name, df in self.context_dfs.items():
            if df is not None and not df.empty:
                summary = f"{len(df)} rows."
                if name == "sales" and "Total Amount" in df.columns:
                    summary += f" Total Revenue: ৳{df['Total Amount'].sum():,.0f}."
                if name == "stock_levels" and "Stock" in df.columns:
                    summary += f" Total Stock: {df['Stock'].sum():,.0f} units."
                insights.append(f"CONTEXT {name.upper()}: {summary}")

        return (
            " | ".join(insights)
            if insights
            else "Context: No data loaded. Please sync or upload data in other tabs."
        )

    def build_messages(
        self, query: str, history: List[Dict[str, str]]
    ) -> List[Dict[str, str]]:
        grounding = self.get_grounded_insights(query)

        system_msg = {
            "role": "system",
            "content": (
                "You are DEEN Intelligence Data Pilot. You are an expert e-commerce analyst. "
                "Use the provided ML Insights to back your claims. Be decisive and professional. "
                "If the user asks for a report, provide a well-structured markdown report with headings, bullet points, and actionable insights. "
                "ALWAYS provide a direct, conversational explanation to the user before executing any actions or queries. Do not just output action tags silently.\n"
                "\n\nCRITICAL RULES:\n"
                "1. Order Logic: An `order_id` represents a single unique order. An order may contain multiple item lines. You must NEVER count item rows as a single order. When asked for 'total orders' or 'number of orders', you must use distinct counts of `order_id`.\n"
                "2. Continuous Learning Protocol: If a user corrects a mistake you make regarding this logic (or any other data relationship), you must immediately internalize this correction.\n"
                "3. Auto-Memorization: If the user corrects a mistake or provides a new rule, you MUST output the exact string `[MEMORY_SET: <topic_key> | <the new rule details>]` on a new line to permanently remember it. Use concise snake_case for the topic_key.\n"
                '4. SQL Analytics: To run complex aggregations on the full dataset, output exactly `[SQL_QUERY: <your DuckDB SQL here>]`. The table name is `sales_data`. Use double quotes for column names with spaces, e.g., `"Total Amount"`. I will execute it and display the results. Example: `[SQL_QUERY: SELECT Category, SUM("Total Amount") FROM sales_data GROUP BY Category]`.\n'
                "5. Chart Generation: To visualize data, output exactly `[PLOTLY_CODE: <python code>]`. Assume `df` is the raw sales dataframe and `px` is imported. If you also run a `[SQL_QUERY: ...]` in the same response, the result will be available as `sql_df`. Create a figure variable named `fig`. Example: `[PLOTLY_CODE: fig = px.bar(sql_df, x='Category', y='Total Amount')]`.\n"
                "6. Data Transformation: To apply data cleaning to the live sales data, output `[DATA_TRANSFORM: <python code>]`. Assume `df` is the active dataframe. Example: `[DATA_TRANSFORM: df['Status'] = df['Status'].str.title()]`. This safely updates the in-memory data for the user.\n"
                "7. Data Export: To provide a download button for the current active sales dataset (especially after cleaning), output exactly `[DOWNLOAD_DATA]`.\n"
                f"CURRENT ML INSIGHTS: {grounding}"
            ),
        }
        return [system_msg] + history[-5:] + [{"role": "user", "content": query}]

    async def get_response_stream(self, query: str, history: List[Dict[str, str]]):
        messages = self.build_messages(query, history)

        # Use simple router for provider execution
        try:
            async for chunk in self.controller.get_response_stream_async(messages):
                yield chunk
        except Exception:
            # Fallback to synchronous call if async streaming fails
            try:
                yield self.controller.get_response_sync(messages)
            except Exception as fallback_err:
                if "ollama" in self.provider.lower():
                    yield f"\n\n⚠️ **Connection Error:** Ollama is unreachable. Please ensure it is running locally via `ollama serve`.\n\n`Details: {fallback_err}`"
                else:
                    yield f"\n\n⚠️ **Error:** Failed to get response from {self.provider}. Please verify your API key and connection.\n\n`Details: {fallback_err}`"
