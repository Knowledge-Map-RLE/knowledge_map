import logging
import re
import uuid
from typing import Optional

from fastapi import APIRouter
from grpc import aio
from pydantic import BaseModel

from utils.generated import nlp_pb2, nlp_pb2_grpc

logger = logging.getLogger(__name__)

router = APIRouter(tags=["article_editor"])

NLP_HOST = "127.0.0.1"
NLP_PORT = 50055


class SplitBlocksRequest(BaseModel):
    text: str


class BlockItem(BaseModel):
    id: str
    type: str
    content: str
    order: int


class SplitBlocksResponse(BaseModel):
    success: bool
    blocks: list[BlockItem] = []


async def _split_sentences_nlp(text: str, timeout: int = 5) -> list[str]:
    channel = aio.insecure_channel(f"{NLP_HOST}:{NLP_PORT}")
    try:
        stub = nlp_pb2_grpc.NLPServiceStub(channel)
        request = nlp_pb2.AnalyzeTextRequest(
            text=text,
            levels=[nlp_pb2.LEVEL_TOKENIZATION],
            enable_voting=False,
        )
        response = await stub.AnalyzeText(request, timeout=timeout)
        return [s.text.strip() for s in response.document.sentences if s.text.strip()]
    except Exception as e:
        logger.warning("NLP gRPC sentence split failed, fallback to regex: %s", e)
        return _split_sentences_regex(text)
    finally:
        await channel.close()


def _split_sentences_regex(text: str) -> list[str]:
    text = re.sub(r'\s+', ' ', text).strip()
    raw = re.split(r'(?<=[.!?])\s+(?=[A-Z"\'(])', text)
    return [s.strip() for s in raw if s.strip()]


def _make_block(type_: str, content: str, order: int) -> BlockItem:
    return BlockItem(
        id=str(uuid.uuid4()),
        type=type_,
        content=content,
        order=order,
    )


def _is_separator_line(line: str) -> bool:
    return bool(re.match(r'^[-*_]{3,}\s*$', line.strip()))


def _is_image_line(line: str) -> bool:
    return bool(re.match(r'^!\[([^\]]*)\]\(([^)]+)\)\s*$', line.strip()))


REGEX_CODE_FENCE = re.compile(r'^```(\w*)\s*$')
REGEX_CODE_CLOSE = re.compile(r'^```\s*$')
REGEX_DOLLAR_OPEN = re.compile(r'^\$\$\s*$')
REGEX_DOLLAR_CLOSE = re.compile(r'^\$\$\s*$')


async def _split_into_blocks_inner(text: str) -> list[BlockItem]:
    if not text or not text.strip():
        return []

    blocks: list[BlockItem] = []
    paragraphs = re.split(r'\n\n+', text)
    order = 0

    for para in paragraphs:
        if not para.strip():
            blocks.append(_make_block("paragraph", "", order))
            order += 1
            continue

        lines = para.rstrip('\n').split('\n')
        cleaned = [l for l in lines if l.strip()]
        if not cleaned:
            continue

        first = cleaned[0].strip()

        # Code fence
        m = REGEX_CODE_FENCE.match(first)
        if m:
            content_lines: list[str] = []
            for l in lines[1:]:
                if REGEX_CODE_CLOSE.match(l.strip()):
                    break
                content_lines.append(l)
            content = '\n'.join(content_lines)
            blocks.append(_make_block("code", content, order))
            order += 1
            continue

        # Formula ($$)
        if REGEX_DOLLAR_OPEN.match(first):
            content_lines = []
            for l in lines[1:]:
                if REGEX_DOLLAR_CLOSE.match(l.strip()):
                    break
                content_lines.append(l)
            content = '\n'.join(content_lines)
            blocks.append(_make_block("formula", content, order))
            order += 1
            continue

        # Separator on its own
        if len(cleaned) == 1 and _is_separator_line(first):
            blocks.append(_make_block("separator", first.rstrip(), order))
            order += 1
            continue

        # Image on its own line
        if len(cleaned) == 1 and _is_image_line(first):
            blocks.append(_make_block("image", first, order))
            order += 1
            continue

        # Table: every non‑empty line has pipe
        if all('|' in l for l in cleaned):
            blocks.append(_make_block("table", '\n'.join(cleaned), order))
            order += 1
            continue

        # Mixed paragraph: process line by line
        lines = para.split('\n')
        prose_parts: list[str] = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                prose_parts.append('')
                continue
            if _is_image_line(stripped):
                blocks.append(_make_block("image", stripped, order))
                order += 1
                continue
            if stripped.startswith('```') or stripped == '```':
                continue
            prose_parts.append(stripped)

        prose_joined = ' '.join(p for p in prose_parts if p).strip()
        if prose_joined:
            sentences = await _split_sentences_nlp(prose_joined)
            for sent in sentences:
                blocks.append(_make_block("sentence", sent, order))
                order += 1

    return blocks


@router.post("/article_editor/split_into_blocks", response_model=SplitBlocksResponse)
async def split_into_blocks(req: SplitBlocksRequest):
    try:
        blocks = await _split_into_blocks_inner(req.text)
        return SplitBlocksResponse(success=True, blocks=blocks)
    except Exception as e:
        logger.exception("split_into_blocks failed")
        return SplitBlocksResponse(success=False, blocks=[])
