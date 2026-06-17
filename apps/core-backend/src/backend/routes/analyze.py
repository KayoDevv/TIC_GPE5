import logging
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, Form, Request, UploadFile
from fastapi.responses import JSONResponse
from zt_shared.models.events import EmailContext, FileRequestedEvent

from backend.auth import JWTPayload
from backend.config import Settings
from backend.dependencies import get_current_user, get_settings
from backend.dtos import AnalyzeResponseDTO, ErrorDTO
from backend.services.hasher import compute_sha256
from backend.services.storage import upload_file

logger = logging.getLogger(__name__)

router = APIRouter()


async def validate_form_fields(
    sender: str | None = Form(default=None),
    subject: str | None = Form(default=None),
    body_text: str = Form(default=""),
) -> dict[str, str]:
    """
    Dependency that validates required form fields.
    Returns a dict with sender, subject, body_text.
    Raises JSONResponse 400 if required fields are missing.
    """
    if not sender or not subject:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=400,
            detail={"error": "MISSING_FIELDS", "message": "Required form fields (sender, subject) are missing."},  # noqa: E501
        )
    return {"sender": sender, "subject": subject, "body_text": body_text}


async def validate_file(
    file: UploadFile,
    settings: Settings = Depends(get_settings),  # noqa: B008
) -> tuple[bytes, str]:
    """
    Dependency that reads the file, checks size, and computes SHA-256.
    Returns (file_bytes, sha256).
    """
    file_bytes = await file.read()

    if len(file_bytes) > settings.max_file_size_bytes:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=400,
            detail={
                "error": "FILE_TOO_LARGE",
                "message": f"File exceeds the {settings.max_file_size_bytes // (1024 * 1024)} MB limit.",  # noqa: E501
            },
        )

    sha256 = await compute_sha256(file_bytes)
    return file_bytes, sha256


@router.post(
    "/analyze",
    status_code=202,
    response_model=AnalyzeResponseDTO,
    responses={
        400: {"model": ErrorDTO},
        401: {"model": ErrorDTO},
        500: {"model": ErrorDTO},
    },
)
async def analyze(
    request: Request,
    file: UploadFile,
    current_user: JWTPayload = Depends(get_current_user),  # noqa: B008
    form_fields: dict[str, str] = Depends(validate_form_fields),  # noqa: B008
    file_data: tuple[bytes, str] = Depends(validate_file),  # noqa: B008
    settings: Settings = Depends(get_settings),  # noqa: B008
) -> AnalyzeResponseDTO | JSONResponse:
    """
    Submit an email attachment for analysis.

    Auth, field validation, and file validation are handled by dependencies.
    This handler only contains business logic:
    1. Upload to S3/MinIO
    2. Publish file.requested to Kafka
    3. Return 202 with job_id
    """
    file_bytes, sha256 = file_data
    job_id = uuid4()
    filename = file.filename or "unknown"

    # --- 1. Upload to S3 ---
    try:
        s3_url = await upload_file(
            s3_client=request.app.state.s3_client,
            bucket=settings.s3_bucket_name,
            job_id=str(job_id),
            filename=filename,
            data=file_bytes,
        )
    except Exception as e:
        logger.error(f"S3 upload failed for job {job_id}: {e}")
        return JSONResponse(
            status_code=500,
            content=ErrorDTO(
                error="UPLOAD_FAILED",
                message="Failed to upload file to storage.",
            ).model_dump(),
        )

    # --- 2. Publish to Kafka ---
    event = FileRequestedEvent(
        job_id=job_id,
        s3_url=s3_url,
        sha256=sha256,
        email_context=EmailContext(
            sender=form_fields["sender"],
            subject=form_fields["subject"],
            body_text=form_fields["body_text"],
        ),
        timestamp=datetime.now(timezone.utc),
    )

    try:
        publisher = request.app.state.publisher
        await publisher.publish(settings.kafka_topic_file_requested, event)
    except Exception as e:
        logger.error(f"Kafka publish failed for job {job_id}: {e}")
        return JSONResponse(
            status_code=500,
            content=ErrorDTO(
                error="KAFKA_PUBLISH_FAILED",
                message="Failed to dispatch analysis job.",
            ).model_dump(),
        )

    logger.info(f"Analysis started: job_id={job_id}, sha256={sha256}")

    return AnalyzeResponseDTO(job_id=job_id)
