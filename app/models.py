from sqlalchemy import Column, Integer, String, BigInteger, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from app.db import Base


# 수집된 프레임 메타데이터를 저장하는 테이블이다.
class Frame(Base):
    __tablename__ = "frames"
    __table_args__ = (
        UniqueConstraint("device_id", "timestamp", name="uq_frame_device_timestamp"),
    )

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String, index=True, nullable=False)
    timestamp = Column(BigInteger, index=True, nullable=False)
    file_path = Column(String, nullable=False)


# 시간 기준으로 묶인 sync group과 dispatch 상태를 저장한다.
class SyncGroup(Base):
    __tablename__ = "sync_groups"

    id = Column(Integer, primary_key=True, index=True)
    group_timestamp = Column(BigInteger, index=True, nullable=False)
    dispatch_status = Column(String, nullable=False, default="pending", index=True)
    last_dispatch_at = Column(BigInteger, nullable=True)
    last_dispatch_status_code = Column(Integer, nullable=True)
    last_dispatch_error = Column(String, nullable=True)
    dispatched_at = Column(BigInteger, nullable=True)
    retry_count = Column(Integer, nullable=False, default=0)
    next_retry_at = Column(BigInteger, nullable=True)

    frames = relationship(
        "SyncFrame",
        back_populates="sync_group",
        cascade="all, delete-orphan"
    )


# sync group과 frame 사이의 연결 관계를 저장한다.
class SyncFrame(Base):
    __tablename__ = "sync_frames"

    id = Column(Integer, primary_key=True, index=True)
    sync_group_id = Column(Integer, ForeignKey("sync_groups.id"), nullable=False)
    frame_id = Column(Integer, ForeignKey("frames.id"), nullable=False)

    sync_group = relationship("SyncGroup", back_populates="frames")
    frame = relationship("Frame")
