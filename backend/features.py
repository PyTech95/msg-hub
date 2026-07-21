"""
NSTU extended features:
  1. PDF Bill Splitter — upload PDF, extract individual bills via LLM, send via SMS/WA/Email
  2. Notice Templates — HTML template + variable fill → PDF → bulk send
  3. AI Voice Calls — TTS script-based campaign (mock TTS in demo mode)

All third-party deliveries (Resend email, ElevenLabs voice) run in mock mode by default.
"""
import os
import io
import json
import uuid
import base64
import asyncio
import secrets
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any

import pdfplumber
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import Response as FastResponse
from pydantic import BaseModel, EmailStr, Field

log = logging.getLogger("nstu.features")

# ---- helpers reused across features --------------------------------------------------
def _now():
    return datetime.now(timezone.utc)

def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()

def _new_id() -> str:
    return str(uuid.uuid4())


def build_features_router(*, db, current_user, require_roles, audit, emit_event, ADAPTERS, cflt,
                          media_fs=None, meta_wa=None, meta_wa_credentials=None, email_service=None):
    """Wire the features router. Pass in references to the main app's dependencies."""
    router = APIRouter(prefix="/api")

    # =====================================================================
    # FEATURE 1 — PDF BILL SPLITTER
    # =====================================================================
    EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")

    async def llm_split_bills(page_texts: List[str]) -> Dict[str, Any]:
        """Use Claude to extract bills + page ranges from a multi-page PDF.

        page_texts: list of per-page extracted text (1-indexed conceptually).
        Returns {bills, error}. Each bill has page_start/page_end (1-indexed inclusive).
        """
        if not EMERGENT_LLM_KEY:
            return {"bills": [], "error": "EMERGENT_LLM_KEY not configured"}
        try:
            from emergentintegrations.llm.chat import LlmChat, UserMessage
        except Exception as e:
            return {"bills": [], "error": f"emergentintegrations import failed: {e}"}

        # Build a page-tagged text blob so the LLM can attribute each bill to specific pages.
        tagged = []
        budget = 18000
        for i, t in enumerate(page_texts, start=1):
            snippet = (t or "").strip()
            header = f"\n===== PAGE {i} =====\n"
            if sum(len(x) for x in tagged) + len(header) + len(snippet) > budget:
                snippet = snippet[: max(0, budget - sum(len(x) for x in tagged) - len(header))]
                tagged.append(header + snippet)
                break
            tagged.append(header + snippet)
        text_blob = "".join(tagged)

        prompt = (
            "You are extracting individual property bills from a multi-bill PDF. "
            "The text below is split by page markers like '===== PAGE N =====' where N is a 1-indexed page number. "
            "Identify each distinct bill block and output JSON with this exact schema:\n"
            '{"bills":[{"name":"...","phone":"...","email":"...","property_id":"...","address":"...","amount":0,"due_date":"YYYY-MM-DD","raw":"...","page_start":1,"page_end":1}]}\n'
            "Rules:\n"
            "- One entry per bill\n"
            "- page_start and page_end are 1-indexed inclusive page numbers where the bill appears (usually the same page)\n"
            "- If a field is missing, leave it as empty string or 0\n"
            "- raw = a 1-line summary of the bill\n"
            "- Strict JSON only, no markdown, no commentary\n\n"
            f"PDF TEXT:\n{text_blob}"
        )

        try:
            chat = LlmChat(
                api_key=EMERGENT_LLM_KEY,
                session_id=f"bill-split-{_new_id()[:8]}",
                system_message="You are a precise document-extraction engine. Return strict JSON only.",
            ).with_model("anthropic", "claude-sonnet-4-5-20250929")
            resp = await chat.send_message(UserMessage(text=prompt))
            text_resp = (resp or "").strip()
            if text_resp.startswith("```"):
                text_resp = text_resp.split("```", 2)[1]
                if text_resp.startswith("json"):
                    text_resp = text_resp[4:]
                text_resp = text_resp.rsplit("```", 1)[0].strip()
            data = json.loads(text_resp)
            return {"bills": data.get("bills", []) or [], "error": None}
        except Exception as e:
            log.error(f"LLM bill split failed: {e}")
            return {"bills": [], "error": str(e)[:300]}

    def _slice_pdf_pages(raw_pdf: bytes, page_start: int, page_end: int) -> Optional[bytes]:
        """Return a new PDF containing pages [page_start..page_end] (1-indexed inclusive)."""
        try:
            from pypdf import PdfReader, PdfWriter
            reader = PdfReader(io.BytesIO(raw_pdf))
            total = len(reader.pages)
            ps = max(1, int(page_start or 1))
            pe = min(total, int(page_end or ps))
            if pe < ps:
                pe = ps
            writer = PdfWriter()
            for i in range(ps - 1, pe):
                writer.add_page(reader.pages[i])
            buf = io.BytesIO()
            writer.write(buf)
            return buf.getvalue()
        except Exception as e:
            log.warning(f"pdf slice failed p{page_start}-{page_end}: {e}")
            return None

    @router.post("/bills/upload")
    async def upload_bill_pdf(file: UploadFile = File(...), user: dict = Depends(current_user)):
        raw = await file.read()
        try:
            with pdfplumber.open(io.BytesIO(raw)) as pdf:
                page_texts = [(p.extract_text() or "") for p in pdf.pages]
                page_count = len(pdf.pages)
        except Exception as e:
            raise HTTPException(400, f"Could not read PDF: {e}")

        if not any(t.strip() for t in page_texts):
            raise HTTPException(400, "PDF has no extractable text (scanned image?)")

        batch_id = _new_id()
        result = await llm_split_bills(page_texts)
        bills = result["bills"]
        llm_error = result["error"]
        rows = []
        base_filename = (file.filename or "bills.pdf").rsplit(".", 1)[0]
        for idx, b in enumerate(bills, start=1):
            bill_id = _new_id()
            ps = int(b.get("page_start") or 1)
            pe = int(b.get("page_end") or ps)
            # Sanitize page bounds
            ps = max(1, min(ps, page_count))
            pe = max(ps, min(pe, page_count))

            pdf_gridfs_id: Optional[str] = None
            pdf_size: int = 0
            if media_fs is not None:
                sliced = _slice_pdf_pages(raw, ps, pe)
                if sliced:
                    safe_name = (b.get("property_id") or b.get("name") or f"bill-{idx}").strip() or f"bill-{idx}"
                    safe_name = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in safe_name)[:40]
                    pdf_filename = f"{base_filename}__{safe_name}__{idx}.pdf"
                    fs_id = await media_fs.upload_from_stream(
                        pdf_filename, io.BytesIO(sliced),
                        metadata={"company_id": user.get("company_id"),
                                  "mime_type": "application/pdf",
                                  "source": "bill_split",
                                  "batch_id": batch_id,
                                  "bill_id": bill_id,
                                  "size": len(sliced),
                                  "created_at": _iso(_now())},
                    )
                    pdf_gridfs_id = str(fs_id)
                    pdf_size = len(sliced)

            rows.append({
                "id": bill_id,
                "batch_id": batch_id,
                "name": (b.get("name") or "").strip(),
                "phone": (b.get("phone") or "").strip(),
                "email": (b.get("email") or "").strip(),
                "property_id": (b.get("property_id") or "").strip(),
                "address": (b.get("address") or "").strip(),
                "amount": float(b.get("amount") or 0),
                "due_date": (b.get("due_date") or "").strip(),
                "raw": (b.get("raw") or "").strip(),
                "page_start": ps,
                "page_end": pe,
                "pdf_gridfs_id": pdf_gridfs_id,
                "pdf_size": pdf_size,
                "sent": {"sms": False, "whatsapp": False, "email": False},
                "company_id": user.get("company_id"),
                "created_at": _iso(_now()),
            })
        if rows:
            await db.bills.insert_many(rows)

        await db.bill_batches.insert_one({
            "id": batch_id,
            "filename": file.filename,
            "page_count": page_count,
            "bill_count": len(rows),
            "uploaded_by": user.get("email"),
            "llm_error": llm_error,
            "created_at": _iso(_now()),
        })
        await audit("bills_uploaded", "bill_batch", batch_id, user, {"filename": file.filename, "bills": len(rows), "llm_error": llm_error})
        if llm_error and not rows:
            raise HTTPException(400, f"AI extraction failed: {llm_error}. PDF text was readable but no bills were parsed. The batch was not saved.")
        return {"batch_id": batch_id, "bill_count": len(rows), "page_count": page_count, "warning": llm_error}

    @router.get("/bills/batches")
    async def list_bill_batches(user: dict = Depends(current_user)):
        return await db.bill_batches.find(cflt(user), {"_id": 0}).sort("created_at", -1).limit(100).to_list(100)

    @router.get("/bills")
    async def list_bills(batch_id: Optional[str] = None, user: dict = Depends(current_user)):
        flt: Dict[str, Any] = cflt(user)
        if batch_id:
            flt["batch_id"] = batch_id
        return await db.bills.find(flt, {"_id": 0}).sort("created_at", -1).limit(2000).to_list(2000)

    @router.delete("/bills/batches/{batch_id}")
    async def delete_bill_batch(batch_id: str, user: dict = Depends(require_roles("super_admin","admin"))):
        # Clean up per-bill PDFs from GridFS first
        if media_fs is not None:
            from bson import ObjectId
            to_delete = await db.bills.find(cflt(user, {"batch_id": batch_id}),
                                            {"_id": 0, "pdf_gridfs_id": 1}).to_list(2000)
            for b in to_delete:
                gid = b.get("pdf_gridfs_id")
                if not gid:
                    continue
                try:
                    await media_fs.delete(ObjectId(gid))
                except Exception as e:
                    log.warning(f"gridfs delete failed for {gid}: {e}")
        await db.bills.delete_many(cflt(user, {"batch_id": batch_id}))
        await db.bill_batches.delete_one(cflt(user, {"id": batch_id}))
        await audit("bill_batch_deleted", "bill_batch", batch_id, user)
        return {"ok": True}

    @router.get("/bills/{bill_id}/pdf")
    async def get_bill_pdf(bill_id: str, user: dict = Depends(current_user)):
        """Stream the per-bill sliced PDF from GridFS. Tenant-scoped."""
        if media_fs is None:
            raise HTTPException(503, "PDF storage not available")
        bill = await db.bills.find_one(cflt(user, {"id": bill_id}), {"_id": 0})
        if not bill:
            raise HTTPException(404, "Bill not found")
        gid = bill.get("pdf_gridfs_id")
        if not gid:
            raise HTTPException(404, "No PDF attached to this bill")
        from bson import ObjectId
        try:
            stream = await media_fs.open_download_stream(ObjectId(gid))
        except Exception:
            raise HTTPException(404, "PDF not found in storage")
        buf = await stream.read()
        safe_name = (bill.get("property_id") or bill.get("name") or "bill").strip() or "bill"
        safe_name = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in safe_name)[:40]
        return FastResponse(content=buf, media_type="application/pdf",
                            headers={"Content-Disposition": f'inline; filename="bill-{safe_name}.pdf"'})

    class BillSendIn(BaseModel):
        channel: str  # sms | whatsapp | email
        bill_ids: List[str]
        message_template: str  # supports {{name}} {{amount}} {{property_id}} {{address}} {{due_date}}
        subject: Optional[str] = None  # for email
        attach_pdf: bool = True  # attach the per-bill sliced PDF (whatsapp/email only)

    def _render(tpl: str, b: dict) -> str:
        for k, v in {
            "name": b.get("name",""),
            "phone": b.get("phone",""),
            "email": b.get("email",""),
            "property_id": b.get("property_id",""),
            "address": b.get("address",""),
            "amount": str(b.get("amount", 0)),
            "due_date": b.get("due_date",""),
            "raw": b.get("raw",""),
        }.items():
            tpl = tpl.replace("{{" + k + "}}", v)
        return tpl

    async def _read_bill_pdf_bytes(bill: dict) -> Optional[bytes]:
        """Fetch the sliced PDF bytes from GridFS for the given bill. Returns None if unavailable."""
        gid = bill.get("pdf_gridfs_id")
        if not gid or media_fs is None:
            return None
        from bson import ObjectId
        try:
            stream = await media_fs.open_download_stream(ObjectId(gid))
            return await stream.read()
        except Exception as e:
            log.warning(f"read bill pdf failed {gid}: {e}")
            return None

    async def _send_whatsapp_bill_pdf(company_id: Optional[str], to_phone: str,
                                     pdf_bytes: bytes, pdf_filename: str,
                                     caption: str) -> Dict[str, Any]:
        """Upload the PDF to Meta and send as a WhatsApp document message."""
        if not meta_wa or not meta_wa_credentials:
            return {"ok": False, "error": "WhatsApp media adapter not wired"}
        creds = await meta_wa_credentials(company_id)
        if not creds:
            return {"ok": False, "error": "WhatsApp not configured for this tenant"}
        try:
            up = await meta_wa.upload_media(creds, pdf_bytes, pdf_filename, "application/pdf")
            if not up.get("ok"):
                return {"ok": False, "error": up.get("error") or "upload failed"}
            resp = await meta_wa.send_media_message(
                creds, to_phone, "document",
                media_id=up["media_id"],
                caption=caption or None,
                filename=pdf_filename,
            )
            return {"ok": True, "provider_message_id": resp.get("provider_message_id")}
        except Exception as e:
            return {"ok": False, "error": str(e)[:300]}

    @router.post("/bills/send")
    async def send_bills(body: BillSendIn, user: dict = Depends(current_user)):
        if body.channel not in ("sms", "whatsapp", "email"):
            raise HTTPException(400, "channel must be sms | whatsapp | email")
        bills = await db.bills.find(cflt(user, {"id": {"$in": body.bill_ids}}), {"_id": 0}).to_list(len(body.bill_ids))
        sent, skipped, no_pdf = 0, 0, 0
        attach_enabled = bool(body.attach_pdf) and body.channel in ("whatsapp", "email")

        for b in bills:
            recipient = b.get("email") if body.channel == "email" else b.get("phone")
            if not recipient:
                skipped += 1; continue
            body_text = _render(body.message_template, b)
            mid = _new_id()
            pdf_filename = f"bill-{(b.get('property_id') or b.get('name') or b['id'])[:32]}.pdf"

            provider_msg_id = None
            status = "queued"
            send_error = None
            attached = False

            if attach_enabled:
                pdf_bytes = await _read_bill_pdf_bytes(b)
                if pdf_bytes:
                    if body.channel == "whatsapp":
                        r = await _send_whatsapp_bill_pdf(user.get("company_id"),
                                                         b.get("phone"), pdf_bytes,
                                                         pdf_filename, body_text)
                        if r.get("ok"):
                            provider_msg_id = r.get("provider_message_id")
                            status = "sent"; attached = True
                        else:
                            send_error = r.get("error")
                    elif body.channel == "email":
                        if email_service is not None:
                            r = await email_service.send(
                                to=recipient,
                                subject=(body.subject or "Your bill"),
                                html=f"<pre style='font-family:inherit;white-space:pre-wrap'>{body_text}</pre>",
                                text=body_text,
                                attachments=[{
                                    "filename": pdf_filename,
                                    "content_b64": base64.b64encode(pdf_bytes).decode(),
                                    "content_type": "application/pdf",
                                }],
                            )
                            if r.get("ok"):
                                provider_msg_id = r.get("id")
                                status = "sent"; attached = True
                            else:
                                send_error = r.get("error")
                else:
                    no_pdf += 1

            # Fallback to text-only adapter path when we didn't already send with attachment
            if not attached:
                adapter = ADAPTERS.get(body.channel)
                if adapter:
                    try:
                        resp = await adapter.send(recipient, body_text, None, company_id=user.get("company_id"))
                        provider_msg_id = resp.get("provider_message_id")
                        status = "sent"
                    except Exception as e:
                        log.error(f"bill send failed: {e}")
                        send_error = str(e)[:300]

            await db.messages.insert_one({
                "id": mid, "channel": body.channel, "contact_id": b["id"],
                "direction": "outbound", "body": body_text,
                "status": status, "provider_message_id": provider_msg_id,
                "campaign_id": None, "company_id": user.get("company_id"),
                "meta": {"bill_id": b["id"], "subject": body.subject,
                         "pdf_attached": attached, "error": send_error},
                "created_at": _iso(_now()), "updated_at": _iso(_now()),
            })
            # Simulate lifecycle only for mock/text sends where we relied on the adapter
            if not attached and status == "sent":
                adapter = ADAPTERS.get(body.channel)
                if adapter:
                    asyncio.create_task(_deliver(mid, body.channel, adapter))

            await db.bills.update_one({"id": b["id"]},
                {"$set": {f"sent.{body.channel}": True,
                          f"sent_at.{body.channel}": _iso(_now()),
                          f"sent_with_pdf.{body.channel}": attached}})
            sent += 1
        await audit("bills_sent", "bills", "", user, {"channel": body.channel, "sent": sent,
                                                     "skipped": skipped, "no_pdf": no_pdf,
                                                     "attach_pdf": attach_enabled})
        return {"sent": sent, "skipped": skipped, "no_pdf": no_pdf,
                "attach_pdf": attach_enabled}

    async def _deliver(mid: str, channel: str, adapter):
        try:
            await adapter.simulate_lifecycle(mid)
        except Exception as e:
            log.error(f"deliver crash {mid}: {e}")

    # =====================================================================
    # FEATURE 2 — NOTICE TEMPLATES (HTML + variables → PDF → bulk send)
    # =====================================================================
    class NoticeTemplateIn(BaseModel):
        name: str
        html: str
        subject: Optional[str] = ""
        description: Optional[str] = ""

    @router.get("/notice-templates")
    async def list_notice_tpls(user: dict = Depends(current_user)):
        return await db.notice_templates.find(cflt(user), {"_id": 0}).sort("created_at", -1).to_list(200)

    @router.post("/notice-templates")
    async def create_notice_tpl(body: NoticeTemplateIn, user: dict = Depends(require_roles("super_admin","admin"))):
        doc = body.model_dump()
        doc["id"] = _new_id()
        doc["created_by"] = user.get("email")
        doc["company_id"] = user.get("company_id")
        doc["created_at"] = _iso(_now())
        await db.notice_templates.insert_one(doc)
        doc.pop("_id", None)
        await audit("notice_template_created", "notice_template", doc["id"], user, {"name": doc["name"]})
        return doc

    @router.patch("/notice-templates/{tpl_id}")
    async def update_notice_tpl(tpl_id: str, body: NoticeTemplateIn, user: dict = Depends(require_roles("super_admin","admin"))):
        await db.notice_templates.update_one(cflt(user, {"id": tpl_id}), {"$set": body.model_dump()})
        return await db.notice_templates.find_one(cflt(user, {"id": tpl_id}), {"_id": 0})

    @router.delete("/notice-templates/{tpl_id}")
    async def delete_notice_tpl(tpl_id: str, user: dict = Depends(require_roles("super_admin","admin"))):
        await db.notice_templates.delete_one(cflt(user, {"id": tpl_id}))
        await audit("notice_template_deleted", "notice_template", tpl_id, user)
        return {"ok": True}

    def _render_html(html: str, vars: Dict[str, Any]) -> str:
        out = html
        for k, v in (vars or {}).items():
            out = out.replace("{{" + str(k) + "}}", str(v) if v is not None else "")
        return out

    def _html_to_pdf_bytes(html: str) -> bytes:
        from weasyprint import HTML
        return HTML(string=html).write_pdf()

    @router.post("/notices/preview")
    async def preview_notice(payload: Dict[str, Any], user: dict = Depends(current_user)):
        """payload = {template_id, variables: {...}}"""
        tpl = await db.notice_templates.find_one(cflt(user, {"id": payload.get("template_id")}), {"_id": 0})
        if not tpl:
            raise HTTPException(404, "Template not found")
        rendered = _render_html(tpl["html"], payload.get("variables") or {})
        pdf = _html_to_pdf_bytes(rendered)
        return FastResponse(content=pdf, media_type="application/pdf",
                            headers={"Content-Disposition": "inline; filename=notice-preview.pdf"})

    class NoticeSendIn(BaseModel):
        template_id: str
        # Either bill_ids OR contact_ids (whichever is provided). Bills carry richer variables.
        bill_ids: Optional[List[str]] = None
        contact_ids: Optional[List[str]] = None
        channel: str = "email"  # email | whatsapp (sms doesn't support attachments)
        message: Optional[str] = "Please find your notice attached."

    @router.post("/notices/send")
    async def send_notices(body: NoticeSendIn, user: dict = Depends(current_user)):
        tpl = await db.notice_templates.find_one(cflt(user, {"id": body.template_id}), {"_id": 0})
        if not tpl:
            raise HTTPException(404, "Template not found")

        rows: List[Dict[str, Any]] = []
        if body.bill_ids:
            rows = await db.bills.find(cflt(user, {"id": {"$in": body.bill_ids}}), {"_id": 0}).to_list(len(body.bill_ids))
            # normalize variables from bill
            for r in rows:
                r["_vars"] = {k: r.get(k, "") for k in ("name","phone","email","property_id","address","amount","due_date","raw")}
                r["_recipient_phone"] = r.get("phone")
                r["_recipient_email"] = r.get("email")
        elif body.contact_ids:
            cs = await db.contacts.find(cflt(user, {"id": {"$in": body.contact_ids}}), {"_id": 0}).to_list(len(body.contact_ids))
            for c in cs:
                c["_vars"] = {"name": c.get("name",""), "phone": c.get("phone",""), "email": c.get("email","")}
                c["_recipient_phone"] = c.get("phone")
                c["_recipient_email"] = c.get("email")
            rows = cs
        else:
            raise HTTPException(400, "Provide bill_ids or contact_ids")

        sent, skipped = 0, 0
        for r in rows:
            recipient = r["_recipient_email"] if body.channel == "email" else r["_recipient_phone"]
            if not recipient:
                skipped += 1; continue
            rendered = _render_html(tpl["html"], r["_vars"])
            pdf_bytes = _html_to_pdf_bytes(rendered)
            attachment_key = f"notice-{r.get('id','x')}-{_new_id()[:6]}.pdf"
            # store PDF in DB (small scale demo); in prod use object storage
            await db.notice_pdfs.insert_one({
                "id": _new_id(),
                "key": attachment_key,
                "template_id": body.template_id,
                "target_id": r.get("id"),
                "recipient": recipient,
                "channel": body.channel,
                "company_id": user.get("company_id"),
                "pdf_b64": base64.b64encode(pdf_bytes).decode(),
                "created_at": _iso(_now()),
            })
            adapter = ADAPTERS.get(body.channel)
            mid = _new_id()
            await db.messages.insert_one({
                "id": mid, "channel": body.channel, "contact_id": r.get("id"),
                "direction": "outbound",
                "body": body.message or "Please find your notice attached.",
                "media_url": f"/api/notices/download/{attachment_key}",
                "status": "queued", "provider_message_id": None,
                "campaign_id": None, "company_id": user.get("company_id"),
                "meta": {"notice_template_id": body.template_id, "attachment": attachment_key},
                "created_at": _iso(_now()), "updated_at": _iso(_now()),
            })
            if adapter:
                try:
                    resp = await adapter.send(recipient, body.message or "Notice attached", f"/api/notices/download/{attachment_key}", company_id=user.get("company_id"))
                    await db.messages.update_one({"id": mid}, {"$set": {"provider_message_id": resp.get("provider_message_id")}})
                    asyncio.create_task(_deliver(mid, body.channel, adapter))
                except Exception as e:
                    log.error(f"notice send failed: {e}")
            sent += 1
        await audit("notices_sent", "notice_template", body.template_id, user, {"channel": body.channel, "sent": sent, "skipped": skipped})
        return {"sent": sent, "skipped": skipped}

    @router.get("/notices/download/{key}")
    async def download_notice(key: str, user: dict = Depends(current_user)):
        rec = await db.notice_pdfs.find_one(cflt(user, {"key": key}), {"_id": 0})
        if not rec:
            raise HTTPException(404, "Not found")
        pdf = base64.b64decode(rec["pdf_b64"])
        return FastResponse(content=pdf, media_type="application/pdf",
                            headers={"Content-Disposition": f"attachment; filename={key}"})

    # =====================================================================
    # FEATURE 3 — AI VOICE CALL CAMPAIGN (script-based TTS)
    # =====================================================================
    class VoiceCampaignIn(BaseModel):
        name: str
        script: str  # supports {{name}}, {{amount}}, etc.
        voice: Optional[str] = "neutral"  # neutral, female, male (mock ignores)
        bill_ids: Optional[List[str]] = None
        contact_ids: Optional[List[str]] = None

    @router.post("/voice-campaigns")
    async def create_voice_campaign(body: VoiceCampaignIn, user: dict = Depends(current_user)):
        # Resolve targets
        targets: List[Dict[str, Any]] = []
        if body.bill_ids:
            rows = await db.bills.find(cflt(user, {"id": {"$in": body.bill_ids}}), {"_id": 0}).to_list(len(body.bill_ids))
            targets = [{"id": r["id"], "phone": r.get("phone",""), "vars": r} for r in rows if r.get("phone")]
        elif body.contact_ids:
            rows = await db.contacts.find(cflt(user, {"id": {"$in": body.contact_ids}}), {"_id": 0}).to_list(len(body.contact_ids))
            targets = [{"id": r["id"], "phone": r.get("phone",""), "vars": r} for r in rows if r.get("phone")]
        else:
            raise HTTPException(400, "Provide bill_ids or contact_ids")

        if not targets:
            raise HTTPException(400, "No targets resolved (all rows missing phone numbers?)")

        camp_id = _new_id()
        company_id = user.get("company_id")
        await db.voice_campaigns.insert_one({
            "id": camp_id, "name": body.name, "script": body.script, "voice": body.voice,
            "target_count": len(targets),
            "stats": {"queued": len(targets), "initiated": 0, "completed": 0, "no-answer": 0, "busy": 0, "failed": 0},
            "status": "running" if targets else "completed",
            "created_by": user.get("email"),
            "company_id": company_id,
            "created_at": _iso(_now()),
        })
        await audit("voice_campaign_started", "voice_campaign", camp_id, user, {"name": body.name, "targets": len(targets)})

        voice_adapter = ADAPTERS.get("voice")
        async def _dispatch():
            for t in targets:
                cid = _new_id()
                rendered_script = _render(body.script, t["vars"])
                await db.call_logs.insert_one({
                    "id": cid, "contact_id": t["id"], "direction": "outbound", "status": "initiated",
                    "duration_sec": 0, "recording_url": None,
                    "provider_call_id": f"mock_{secrets.token_hex(6)}",
                    "notes": f"AI script ({body.voice}): {rendered_script[:200]}",
                    "voice_campaign_id": camp_id,
                    "company_id": company_id,
                    "started_at": _iso(_now()), "ended_at": None,
                    "created_at": _iso(_now()),
                })
                await db.usage_records.insert_one({
                    "id": _new_id(), "channel": "voice", "message_id": cid, "units": 1,
                    "amount": 1.20, "currency": "INR", "company_id": company_id, "created_at": _iso(_now()),
                })
                await db.voice_campaigns.update_one({"id": camp_id}, {"$inc": {"stats.initiated": 1}})

                async def _ring(call_id=cid):
                    try:
                        await voice_adapter.simulate_lifecycle(call_id)
                        fresh = await db.call_logs.find_one({"id": call_id}, {"_id": 0})
                        st = (fresh or {}).get("status", "completed")
                        await db.voice_campaigns.update_one({"id": camp_id}, {"$inc": {f"stats.{st}": 1}})
                    except Exception as e:
                        log.error(f"voice ring failed: {e}")
                asyncio.create_task(_ring())
                await asyncio.sleep(0.1)
            await db.voice_campaigns.update_one({"id": camp_id}, {"$set": {"status": "completed", "completed_at": _iso(_now())}})
        asyncio.create_task(_dispatch())
        return {"id": camp_id, "queued": len(targets)}

    @router.get("/voice-campaigns")
    async def list_voice_campaigns(user: dict = Depends(current_user)):
        return await db.voice_campaigns.find(cflt(user), {"_id": 0}).sort("created_at", -1).limit(100).to_list(100)

    @router.get("/voice-campaigns/{camp_id}")
    async def get_voice_campaign(camp_id: str, user: dict = Depends(current_user)):
        c = await db.voice_campaigns.find_one(cflt(user, {"id": camp_id}), {"_id": 0})
        if not c:
            raise HTTPException(404, "Not found")
        calls = await db.call_logs.find(cflt(user, {"voice_campaign_id": camp_id}), {"_id": 0}).sort("created_at", -1).limit(500).to_list(500)
        return {"campaign": c, "calls": calls}

    # =====================================================================
    # FEATURE 4 — SMART REMINDER AUTOMATION
    # Auto-escalates: T-7 days → SMS, T-3 days → WhatsApp, T-1 day → AI Voice call
    # =====================================================================
    DEFAULT_STEPS = [
        {"days_before": 7, "channel": "sms",
         "template": "Reminder: Hi {{name}}, your property bill #{{property_id}} for INR {{amount}} is due on {{due_date}}. Please pay to avoid penalty."},
        {"days_before": 3, "channel": "whatsapp",
         "template": "⏰ Hi {{name}}, just 3 days left to pay your property bill #{{property_id}} (INR {{amount}}). Due {{due_date}}."},
        {"days_before": 1, "channel": "voice",
         "template": "Hello {{name}}, this is an urgent automated reminder. Your property bill of INR {{amount}} for property {{property_id}} is due tomorrow on {{due_date}}. Please pay immediately to avoid penalty."},
    ]

    class EnableRemindersIn(BaseModel):
        bill_ids: List[str] = Field(..., min_length=1)
        steps: Optional[List[Dict[str, Any]]] = None  # override default

    @router.post("/bills/enable-reminders")
    async def enable_reminders(body: EnableRemindersIn, user: dict = Depends(current_user)):
        steps = body.steps or DEFAULT_STEPS
        bills = await db.bills.find(cflt(user, {"id": {"$in": body.bill_ids}}), {"_id": 0}).to_list(len(body.bill_ids))
        created = 0; skipped = 0
        for b in bills:
            dd = (b.get("due_date") or "").strip()
            if not dd:
                skipped += 1; continue
            try:
                due_dt = datetime.fromisoformat(dd + "T09:00:00+00:00")
            except Exception:
                try:
                    due_dt = datetime.strptime(dd, "%Y-%m-%d").replace(hour=9, tzinfo=timezone.utc)
                except Exception:
                    skipped += 1; continue
            # remove any existing pending schedules for this bill
            await db.reminder_schedules.delete_many({"bill_id": b["id"], "status": "pending"})
            for idx, step in enumerate(steps):
                fire_at = due_dt - timedelta(days=int(step["days_before"]))
                await db.reminder_schedules.insert_one({
                    "id": _new_id(),
                    "bill_id": b["id"],
                    "step_index": idx,
                    "days_before": int(step["days_before"]),
                    "channel": step["channel"],
                    "template": step["template"],
                    "scheduled_at": _iso(fire_at),
                    "status": "pending",  # pending | fired | skipped | cancelled
                    "company_id": b.get("company_id"),
                    "fired_at": None,
                    "created_at": _iso(_now()),
                })
                created += 1
            await db.bills.update_one({"id": b["id"]}, {"$set": {"auto_remind": True}})
        await audit("reminders_enabled", "bills", "", user, {"bills": len(bills), "created": created})
        return {"created": created, "skipped": skipped, "bills_enabled": len(bills) - skipped}

    @router.post("/bills/{bill_id}/mark-paid")
    async def mark_bill_paid(bill_id: str, user: dict = Depends(current_user)):
        existing = await db.bills.find_one(cflt(user, {"id": bill_id}), {"_id": 0, "id": 1})
        if not existing:
            raise HTTPException(404, "Bill not found")
        await db.bills.update_one(cflt(user, {"id": bill_id}), {"$set": {"paid": True, "paid_at": _iso(_now())}})
        result = await db.reminder_schedules.update_many(
            {"bill_id": bill_id, "status": "pending"},
            {"$set": {"status": "cancelled"}},
        )
        await audit("bill_marked_paid", "bill", bill_id, user, {"cancelled_schedules": result.modified_count})
        return {"ok": True, "cancelled": result.modified_count}

    @router.get("/bills/{bill_id}/schedules")
    async def list_bill_schedules(bill_id: str, user: dict = Depends(current_user)):
        return await db.reminder_schedules.find(cflt(user, {"bill_id": bill_id}), {"_id": 0}).sort("scheduled_at", 1).to_list(50)

    @router.get("/reminders/upcoming")
    async def list_upcoming_reminders(user: dict = Depends(current_user)):
        rows = await db.reminder_schedules.find(cflt(user, {"status": "pending"}), {"_id": 0}).sort("scheduled_at", 1).limit(200).to_list(200)
        # enrich with bill
        bill_ids = list({r["bill_id"] for r in rows})
        bs = await db.bills.find({"id": {"$in": bill_ids}}, {"_id": 0}).to_list(len(bill_ids))
        bmap = {b["id"]: b for b in bs}
        for r in rows:
            b = bmap.get(r["bill_id"]) or {}
            r["bill"] = {"name": b.get("name"), "property_id": b.get("property_id"), "amount": b.get("amount"), "phone": b.get("phone"), "email": b.get("email"), "paid": b.get("paid", False)}
        return rows

    async def reminder_loop():
        """Background task: every 60s, fire any pending reminders whose scheduled_at <= now."""
        log.info("reminder scheduler started")
        while True:
            try:
                now = _now()
                pending = await db.reminder_schedules.find({"status": "pending"}, {"_id": 0}).to_list(500)
                for r in pending:
                    try:
                        when = datetime.fromisoformat(r["scheduled_at"].replace("Z","+00:00"))
                    except Exception:
                        continue
                    if when > now:
                        continue
                    bill = await db.bills.find_one({"id": r["bill_id"]}, {"_id": 0})
                    if not bill or bill.get("paid"):
                        await db.reminder_schedules.update_one({"id": r["id"]}, {"$set": {"status": "skipped", "fired_at": _iso(now)}})
                        continue
                    ch = r["channel"]
                    rendered = _render(r["template"], bill)
                    recipient = bill.get("email") if ch == "email" else bill.get("phone")
                    if not recipient:
                        await db.reminder_schedules.update_one({"id": r["id"]}, {"$set": {"status": "skipped", "fired_at": _iso(now), "reason": "no_recipient"}})
                        continue
                    if ch == "voice":
                        # use voice adapter
                        cid = _new_id()
                        await db.call_logs.insert_one({
                            "id": cid, "contact_id": bill["id"], "direction": "outbound", "status": "initiated",
                            "duration_sec": 0, "recording_url": None,
                            "provider_call_id": f"mock_{secrets.token_hex(6)}",
                            "notes": f"Auto-reminder T-{r['days_before']}d: {rendered[:200]}",
                            "voice_campaign_id": None,
                            "company_id": r.get("company_id"),
                            "started_at": _iso(now), "ended_at": None,
                            "created_at": _iso(now),
                        })
                        await db.usage_records.insert_one({
                            "id": _new_id(), "channel": "voice", "message_id": cid, "units": 1,
                            "amount": 1.20, "currency": "INR", "company_id": r.get("company_id"), "created_at": _iso(now),
                        })
                        adapter = ADAPTERS.get("voice")
                        if adapter:
                            asyncio.create_task(_deliver(cid, "voice", adapter))
                    else:
                        adapter = ADAPTERS.get(ch)
                        if not adapter: continue
                        mid = _new_id()
                        await db.messages.insert_one({
                            "id": mid, "channel": ch, "contact_id": bill["id"], "direction": "outbound",
                            "body": rendered, "status": "queued", "provider_message_id": None,
                            "campaign_id": None, "company_id": r.get("company_id"),
                            "meta": {"reminder": True, "bill_id": bill["id"], "days_before": r["days_before"]},
                            "created_at": _iso(now), "updated_at": _iso(now),
                        })
                        try:
                            resp = await adapter.send(recipient, rendered, None, company_id=r.get("company_id"))
                            await db.messages.update_one({"id": mid}, {"$set": {"provider_message_id": resp.get("provider_message_id")}})
                            asyncio.create_task(_deliver(mid, ch, adapter))
                        except Exception as e:
                            log.error(f"reminder send failed: {e}")
                    await db.reminder_schedules.update_one({"id": r["id"]}, {"$set": {"status": "fired", "fired_at": _iso(now)}})
                    await audit("reminder_fired", "bill", r["bill_id"], None, {"channel": ch, "days_before": r["days_before"]})
            except Exception as e:
                log.error(f"reminder loop error: {e}")
            await asyncio.sleep(60)

    @router.on_event("startup")
    async def _start_reminder_loop():
        asyncio.create_task(reminder_loop())

    # =====================================================================
    # FEATURE 5 — Invoice PDF download (WeasyPrint)
    # =====================================================================
    @router.get("/export/invoice/{month}.pdf")
    async def export_invoice_pdf(month: str, user: dict = Depends(require_roles("super_admin","admin"))):
        markup_row = await db.system_settings.find_one({"key": "markup_pct"}, {"_id": 0})
        markup = (markup_row or {}).get("value", {}) or {}
        records = await db.usage_records.find(
            cflt(user, {"created_at": {"$regex": f"^{month}"}}), {"_id": 0}
        ).limit(20000).to_list(20000)
        by_ch: Dict[str, Dict[str, Any]] = {}
        for r in records:
            ch = r["channel"]
            bm = by_ch.setdefault(ch, {"channel": ch, "units": 0, "base": 0, "markup_pct": float(markup.get(ch, 0))})
            bm["units"] += r["units"]
            bm["base"] = round(bm["base"] + r["amount"], 2)
            bm["billable"] = round(bm["base"] * (1 + bm["markup_pct"] / 100.0), 2)

        total_base = round(sum(c["base"] for c in by_ch.values()), 2)
        total_bill = round(sum(c["billable"] for c in by_ch.values()), 2)
        total_units = sum(c["units"] for c in by_ch.values())

        rows_html = ""
        for c in by_ch.values():
            rows_html += f"<tr><td>{c['channel'].upper()}</td><td style='text-align:right'>{c['units']}</td><td style='text-align:right'>₹{c['base']:.2f}</td><td style='text-align:right'>{c['markup_pct']}%</td><td style='text-align:right'><b>₹{c['billable']:.2f}</b></td></tr>"

        html = f"""<!doctype html><html><body style="font-family: Georgia, serif; padding: 48px; color: #111; max-width: 800px;">
          <div style="border-bottom: 4px solid #000; padding-bottom: 12px; margin-bottom: 32px; display:flex; justify-content:space-between; align-items:flex-end;">
            <div>
              <div style="text-transform: uppercase; letter-spacing: 0.2em; font-size: 11px; color:#F97316;">tezsandesh.digital · Communications Platform</div>
              <h1 style="margin: 4px 0 0; font-size: 32px; letter-spacing:-0.02em;">INVOICE</h1>
            </div>
            <div style="text-align:right;">
              <div style="font-size: 24px; font-family: 'IBM Plex Mono', monospace; font-weight: bold;">{month}</div>
              <div style="font-size: 11px; color: #666;">Generated {_iso(_now())[:10]}</div>
            </div>
          </div>
          <table style="width:100%; border-collapse: collapse; margin-bottom: 24px;">
            <thead><tr style="background:#000; color:#fff;">
              <th style="padding:10px; text-align:left;">Channel</th>
              <th style="padding:10px; text-align:right;">Units</th>
              <th style="padding:10px; text-align:right;">Base (INR)</th>
              <th style="padding:10px; text-align:right;">Markup</th>
              <th style="padding:10px; text-align:right;">Billable (INR)</th>
            </tr></thead>
            <tbody>{rows_html}</tbody>
            <tfoot><tr style="background:#f3f3f3; font-weight:bold;">
              <td style="padding:10px;">TOTAL</td>
              <td style="padding:10px; text-align:right;">{total_units}</td>
              <td style="padding:10px; text-align:right;">₹{total_base:.2f}</td>
              <td style="padding:10px;"></td>
              <td style="padding:10px; text-align:right; font-size:18px;">₹{total_bill:.2f}</td>
            </tr></tfoot>
          </table>
          <div style="font-size: 11px; color: #666; border-top: 1px solid #ddd; padding-top: 16px;">
            Records: {len(records)} · Currency: INR · This invoice reflects billable communications usage during {month}.
          </div>
        </body></html>"""
        pdf = _html_to_pdf_bytes(html)
        return FastResponse(content=pdf, media_type="application/pdf",
                            headers={"Content-Disposition": f"attachment; filename=invoice-{month}.pdf"})

    return router
