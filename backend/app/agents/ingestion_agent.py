"""STAGE 01 - Ingestion Agent

Mockup behaviour: 'Auto-capture · raw file stored immutably · metadata logged ·
password-protected file handling', plus memory recall and a dedup message.

Full implementation:
  1. Read the immutable original from blob storage (written at intake).
  2. Password handling: supplied password -> vault -> else pause in
     'awaiting-password' (UI shows the unlock modal, optional 'remember').
  3. Parse: encoding + delimiter sniffing (CSV), multi-sheet selection and
     title-row skipping (Excel), header de-duplication, empty-row removal.
  4. Classify premium vs claims from headers + filename.
  5. Memory recall: prior runs (episodic) + approved mappings (semantic).
  6. Structural-change detection vs the coverholder's last layout.
  7. Persist parsed rows as the 'parsed' dataset and the metadata on the run.
"""
from app.agents.base import BaseAgent
from app.memory import episodic, semantic
from app.parsers.base import PasswordRequired, UnsupportedFile
from app.parsers.detect import detect_file_type
from app.parsers.factory import parse_bytes
from app.security.vault import get_vault
from app.services.intake import raw_key
from app.storage.factory import get_store, save_dataset


class AwaitingPassword(Exception):
    pass


class IngestionFailed(Exception):
    pass


class IngestionAgent(BaseAgent):
    name = "Ingestion Agent"

    def run(self, password: str | None = None, remember_password: bool = False, sheet: str | None = None) -> None:
        f, run, db = self.ctx.file, self.ctx.run, self.ctx.db
        data = get_store().get_raw(raw_key(f))

        if f.password_protected and not password:
            password = get_vault().get(f.coverholder_name)
            if password:
                self.log("Password recalled from vault", f"Coverholder: {f.coverholder_name}")
        try:
            parsed = parse_bytes(f.filename, data, password=password,
                                 sheet=sheet if self.ctx.settings["processing"]["multi_sheet_detection"] else None)
        except PasswordRequired as e:
            f.status, f.error = "awaiting-password", str(e)
            self.log("Password required", f"{f.filename}: {e}. Waiting for analyst to unlock.", "warn")
            raise AwaitingPassword(str(e))
        except UnsupportedFile as e:
            f.status, f.error = "failed", str(e)
            self.log("Parse failed", str(e), "error")
            raise IngestionFailed(str(e))

        if password and remember_password:
            get_vault().set(f.coverholder_name, password)
            self.log("Password saved to vault", f.coverholder_name)

        if not parsed.headers or not parsed.rows:
            f.status, f.error = "failed", "No data rows found"
            self.log("Empty file", "No header/data rows detected", "error")
            raise IngestionFailed("empty file")

        file_type, conf = detect_file_type(f.filename, parsed.headers)
        f.file_type, f.record_count = file_type, len(parsed.rows)

        history = episodic.history(db, f.coverholder_name)
        recalled = semantic.recall(db, f.coverholder_name, file_type)
        change = (episodic.structural_change(db, f.coverholder_name, file_type, parsed.headers)
                  if self.ctx.settings["processing"]["structural_change_detection"] else {"changed": False})

        run.ingestion = {
            "filename": f.filename, "coverholder": f.coverholder_name, "source": f.source,
            "format": parsed.fmt, "encoding": parsed.encoding, "delimiter": parsed.delimiter,
            "sheet": parsed.sheet_name, "sheets": parsed.sheets, "header_row_index": parsed.header_row_index,
            "records": len(parsed.rows), "columns": len(parsed.headers), "headers": parsed.headers,
            "dropped_empty_rows": parsed.dropped_empty_rows, "file_type": file_type,
            "file_type_confidence": round(conf * 100), "sha256": f.sha256, "raw_uri": f.raw_uri,
            "immutable_raw": True, "warnings": parsed.warnings,
            "memory": {"prior_runs": history, "recalled_mappings": len(recalled)},
        }
        run.structural_change = change
        self.ctx.cache["parsed"] = parsed.rows
        self.ctx.cache["headers"] = parsed.headers
        save_dataset(run.id, "parsed", parsed.rows, {"headers": parsed.headers})

        self.log("File captured", f"{len(parsed.rows)} records, {len(parsed.headers)} columns, "
                                  f"{parsed.fmt.upper()}{' sheet ' + parsed.sheet_name if parsed.sheet_name else ''}; "
                                  f"classified as {file_type} ({round(conf*100)}%)")
        for w in parsed.warnings:
            self.log("Parse note", w)
        if history:
            h = history[0]
            self.log("Memory recall", f"Last processed {h['at'][:10]}: quality {h['quality']}%, {h['exceptions']} exceptions")
        else:
            self.log("Memory recall", f"First run for {f.coverholder_name}")
        if change.get("changed"):
            self.log("Structural change detected",
                     f"Added: {change['added'] or '-'}; removed: {change['removed'] or '-'}"
                     f"{'; column order changed' if change.get('order_changed') else ''}", "warn")
