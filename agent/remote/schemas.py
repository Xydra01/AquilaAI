"""Pydantic request/response models for the Remote Companion API."""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class InstanceInfo(BaseModel):
    """Lightweight view of an Aquila instance for the client picker."""

    id: str
    display_name: str
    specialty: str = ""
    default_mode: str = "chat"
    ollama_model: Optional[str] = None


class PairRequest(BaseModel):
    host_id: str = Field(..., description="Host ID shown on the host machine")
    pairing_code: str = Field(..., description="One-time 6-digit pairing code")
    device_name: str = Field("device", description="Friendly name for this device")


class PairResponse(BaseModel):
    token: str
    host_id: str
    device_name: str


class DeviceInfo(BaseModel):
    name: str
    created_at: str
    last_seen_at: str = ""
    token_id: str


class RevokeRequest(BaseModel):
    token_id: str


class EngineStatus(BaseModel):
    engine: Literal["tq", "stock"]
    base_url: str
    up: bool
    managed_pid: Optional[int] = None
    loaded_models: list[str] = Field(default_factory=list)


class ServerStatus(BaseModel):
    engines: list[EngineStatus] = Field(default_factory=list)


class ServerActionRequest(BaseModel):
    engine: Literal["tq", "stock"]
    stop_other: bool = False


class ServerActionResponse(BaseModel):
    ok: bool
    message: str
    engine: Optional[str] = None
    pid: Optional[int] = None
    needs_confirm: bool = False


class ModelActionRequest(BaseModel):
    model: Optional[str] = None
    all_loaded: bool = False


class ModelActionResponse(BaseModel):
    ok: bool
    message: str


class ChatRequest(BaseModel):
    """Payload sent by the client over the chat WebSocket."""

    instance_id: Optional[str] = None
    mode: str = "chat"
    message: str
    light_research: bool = False
    light_coding: bool = False
    light_coding_repo: Optional[str] = None
    light_coding_block: Optional[str] = None
    bounded_tools: bool = False
    history: list[dict[str, Any]] = Field(default_factory=list)
    thread_id: Optional[str] = None
    upload_tokens: list[str] = Field(default_factory=list)
    # Workspace routing (character / learn). Unused for plain chat.
    persona_id: Optional[str] = None
    course_id: Optional[str] = None
    node_id: Optional[str] = None
    archive_id: Optional[str] = None


class ChatEditRequest(BaseModel):
    instance_id: Optional[str] = None
    text: str


class ChatThreadRequest(BaseModel):
    instance_id: Optional[str] = None


class ChatForkRequest(BaseModel):
    instance_id: Optional[str] = None
    source_thread_id: str
    upto_index: Optional[int] = None
    title_hint: str = ""


class UploadResponse(BaseModel):
    upload_token: str
    file_names: list[str] = Field(default_factory=list)
    has_images: bool = False


class PersonaCreateRequest(BaseModel):
    instance_id: Optional[str] = None
    display_name: str
    description: str = ""
    research_lore: bool = False


class PreferencesRequest(BaseModel):
    instance_id: Optional[str] = None
    text: str = ""


class CourseCreateRequest(BaseModel):
    instance_id: Optional[str] = None
    title: str
    topic: str = ""
    intake: str = "files"
    web: bool = False


class ArchiveCreateRequest(BaseModel):
    instance_id: Optional[str] = None
    title: str


class RuntimeSettingsView(BaseModel):
    ollama_engine: str = "stock"
    ollama_base_url: str
    ollama_model: str
    ollama_num_ctx: Optional[int] = None
    searxng_base_url: str
    searxng_engines: str


class RuntimeSettingsUpdate(BaseModel):
    ollama_engine: Optional[str] = None
    ollama_base_url: Optional[str] = None
    ollama_model: Optional[str] = None
    ollama_num_ctx: Optional[int] = None
    searxng_base_url: Optional[str] = None
    searxng_engines: Optional[str] = None


class EnvVariableView(BaseModel):
    key: str
    default_value: str
    current_value: str
    description: str
    inferred_type: str


class EnvSectionView(BaseModel):
    title: str
    variables: list[EnvVariableView]


class EnvUpdateRequest(BaseModel):
    updates: dict[str, str]


class OllamaActiveRequest(BaseModel):
    engine: Literal["tq", "stock"]
    model: Optional[str] = None


class OllamaModelsResponse(BaseModel):
    engine: str
    models: list[str] = Field(default_factory=list)


class SearchStatusResponse(BaseModel):
    ok: bool
    message: str = ""
    docker: dict = Field(default_factory=dict)


class McpServerView(BaseModel):
    name: str
    transport: str = "stdio"
    command: str = ""
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    url: str = ""
    enabled: bool = False
    allowed_modes: list[str] = Field(default_factory=list)


class McpServersResponse(BaseModel):
    servers: list[McpServerView] = Field(default_factory=list)
    health: dict = Field(default_factory=dict)


class McpServersUpdate(BaseModel):
    servers: list[McpServerView] = Field(default_factory=list)


class McpTestResponse(BaseModel):
    ok: bool
    name: str = ""
    status: str = ""
    tool_count: int = 0
    error: str = ""
