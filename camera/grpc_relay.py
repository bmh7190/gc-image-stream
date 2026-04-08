import json
from dataclasses import dataclass


SERVICE_NAME = "gc_image_stream.FrameRelayService"
METHOD_NAME = "StreamFrames"
METHOD_PATH = f"/{SERVICE_NAME}/{METHOD_NAME}"


# relay로 넘길 단일 프레임 데이터다.
@dataclass(frozen=True)
class RelayFrame:
    device_id: str
    timestamp_ms: int
    sequence: int
    content_type: str
    image_bytes: bytes
    file_path: str | None = None


# stream 종료 시 processing server가 돌려주는 응답이다.
@dataclass(frozen=True)
class RelayAck:
    success: bool
    received_count: int
    message: str = ""


# relay 프레임을 메타데이터 길이 + JSON + 이미지 바이트 형식으로 직렬화한다.
def serialize_relay_frame(frame: RelayFrame) -> bytes:
    metadata = {
        "device_id": frame.device_id,
        "timestamp_ms": frame.timestamp_ms,
        "sequence": frame.sequence,
        "content_type": frame.content_type,
        "file_path": frame.file_path,
    }
    metadata_bytes = json.dumps(metadata, separators=(",", ":")).encode("utf-8")
    return len(metadata_bytes).to_bytes(8, "big") + metadata_bytes + frame.image_bytes


# 직렬화된 relay 프레임을 다시 객체로 복원한다.
def deserialize_relay_frame(payload: bytes) -> RelayFrame:
    metadata_length = int.from_bytes(payload[:8], "big")
    metadata_start = 8
    metadata_end = metadata_start + metadata_length
    metadata = json.loads(payload[metadata_start:metadata_end].decode("utf-8"))
    image_bytes = payload[metadata_end:]

    return RelayFrame(
        device_id=metadata["device_id"],
        timestamp_ms=metadata["timestamp_ms"],
        sequence=metadata["sequence"],
        content_type=metadata["content_type"],
        image_bytes=image_bytes,
        file_path=metadata.get("file_path"),
    )


# relay 응답을 JSON으로 직렬화한다.
def serialize_relay_ack(ack: RelayAck) -> bytes:
    return json.dumps(
        {
            "success": ack.success,
            "received_count": ack.received_count,
            "message": ack.message,
        },
        separators=(",", ":"),
    ).encode("utf-8")


# relay 응답 JSON을 객체로 복원한다.
def deserialize_relay_ack(payload: bytes) -> RelayAck:
    data = json.loads(payload.decode("utf-8"))
    return RelayAck(
        success=bool(data["success"]),
        received_count=int(data["received_count"]),
        message=data.get("message", ""),
    )


# gRPC 채널에서 frame relay streaming stub를 만든다.
def build_frame_relay_stub(channel):
    return channel.stream_unary(
        METHOD_PATH,
        request_serializer=serialize_relay_frame,
        response_deserializer=deserialize_relay_ack,
    )


# 테스트/프로토타입용 generic gRPC relay handler를 서버에 등록한다.
def add_frame_relay_servicer(server, frame_handler):
    import grpc

    def stream_frames(request_iterator, context):
        received_count = 0

        for frame in request_iterator:
            received_count += 1
            frame_handler(frame)

        return RelayAck(
            success=True,
            received_count=received_count,
            message="relay stream completed",
        )

    generic_handler = grpc.method_handlers_generic_handler(
        SERVICE_NAME,
        {
            METHOD_NAME: grpc.stream_unary_rpc_method_handler(
                stream_frames,
                request_deserializer=deserialize_relay_frame,
                response_serializer=serialize_relay_ack,
            )
        },
    )
    server.add_generic_rpc_handlers((generic_handler,))
