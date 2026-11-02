import os
import shutil
import uuid
from pathlib import Path
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from basic_pitch import ICASSP_2022_MODEL_PATH
from basic_pitch.inference import predict_and_save, Model

app = FastAPI(title="Vocalis")
basic_pitch_model = Model(ICASSP_2022_MODEL_PATH)

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
STATIC_DIR = BASE_DIR / "static"

UPLOAD_DIR.mkdir(exist_ok=True)
STATIC_DIR.mkdir(exist_ok=True)

# アップロードされたMIDIファイルへの直接アクセス用
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

AUDIO_EXTENSIONS = {".wav", ".mp3", ".ogg", ".flac", ".m4a"}
MIDI_EXTENSIONS = {".mid", ".midi"}


@app.get("/", response_class=HTMLResponse)
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/files")
def list_files():
    files = []
    for p in UPLOAD_DIR.iterdir():
        if p.is_file() and p.suffix.lower() in MIDI_EXTENSIONS and not p.name.startswith("temp_"):
            stat = p.stat()
            files.append(
                {
                    "filename": p.name,
                    "midi_url": f"/uploads/{p.name}",
                    "mtime": stat.st_mtime,
                    "size": stat.st_size,
                }
            )
    files.sort(key=lambda x: x["mtime"], reverse=True)
    return {"files": files}


@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    raw_name = Path(file.filename).name
    suffix = Path(raw_name).suffix.lower()
    stem = Path(raw_name).stem

    if suffix not in (AUDIO_EXTENSIONS | MIDI_EXTENSIONS):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file format. Supported: {AUDIO_EXTENSIONS | MIDI_EXTENSIONS}",
        )

    # 1. MIDIファイルが送られた場合: 元のファイル名で uploads/ に保存（既存ならそのまま返す）
    if suffix in MIDI_EXTENSIONS:
        target_name = raw_name
        target_path = UPLOAD_DIR / target_name

        if target_path.exists():
            return {
                "filename": target_name,
                "midi_url": f"/uploads/{target_name}",
                "cached": True,
            }

        with open(target_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        return {
            "filename": target_name,
            "midi_url": f"/uploads/{target_name}",
            "cached": False,
        }

    # 2. 音声ファイルが送られた場合: 同名の .mid が既に存在すれば変換をスキップ
    final_midi_name = f"{stem}.mid"
    final_midi_path = UPLOAD_DIR / final_midi_name

    if final_midi_path.exists():
        return {
            "filename": final_midi_name,
            "midi_url": f"/uploads/{final_midi_name}",
            "cached": True,
        }

    file_id = uuid.uuid4().hex[:10]
    temp_audio_name = f"temp_{file_id}{suffix}"
    temp_audio_path = UPLOAD_DIR / temp_audio_name

    with open(temp_audio_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        # basic-pitch による推論 & uploads/ への直接MIDI保存
        # 出力名は: {temp_audio_name}_basic_pitch.mid となる
        predict_and_save(
            audio_path_list=[str(temp_audio_path)],
            output_directory=str(UPLOAD_DIR),
            save_midi=True,
            sonify_midi=False,
            save_model_outputs=False,
            save_notes=False,
            model_or_model_path=basic_pitch_model,
        )

        generated_midi_name = f"{temp_audio_name.rsplit('.', 1)[0]}_basic_pitch.mid"
        generated_midi_path = UPLOAD_DIR / generated_midi_name

        if generated_midi_path.exists():
            generated_midi_path.replace(final_midi_path)
        else:
            raise HTTPException(status_code=500, detail="MIDI generation failed.")

        return {
            "filename": final_midi_name,
            "midi_url": f"/uploads/{final_midi_name}",
            "cached": False,
        }

    finally:
        # 抽出完了後、一時音声ファイルは削除
        if temp_audio_path.exists():
            temp_audio_path.unlink()
