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


@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    suffix = Path(file.filename).suffix.lower()
    file_id = uuid.uuid4().hex[:10]

    # 1. MIDIファイルが送られた場合: そのまま uploads/ に保存
    if suffix in MIDI_EXTENSIONS:
        target_name = f"{file_id}_{file.filename}"
        target_path = UPLOAD_DIR / target_name

        with open(target_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        return {"filename": target_name, "midi_url": f"/uploads/{target_name}"}

    # 2. 音声ファイルが送られた場合: 一時保存して basic-pitch で変換
    elif suffix in AUDIO_EXTENSIONS:
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
            final_midi_name = f"{file_id}_{Path(file.filename).stem}.mid"

            # 扱いやすいファイル名にリネーム
            generated_midi_path = UPLOAD_DIR / generated_midi_name
            final_midi_path = UPLOAD_DIR / final_midi_name

            if generated_midi_path.exists():
                generated_midi_path.rename(final_midi_path)
            else:
                raise HTTPException(status_code=500, detail="MIDI generation failed.")

            return {"filename": final_midi_name, "midi_url": f"/uploads/{final_midi_name}"}

        finally:
            # 抽出完了後、一時音声ファイルは削除
            if temp_audio_path.exists():
                temp_audio_path.unlink()

    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file format. Supported: {AUDIO_EXTENSIONS | MIDI_EXTENSIONS}",
        )
