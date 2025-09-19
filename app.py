from flask import Flask, render_template, request, jsonify
import os
import json
from PIL import Image, ImageDraw
from datetime import datetime
import subprocess
import pygetwindow as gw
from vivogpt import *
from langchain.document_loaders import TextLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from sklearn.feature_extraction.text import TfidfVectorizer
import numpy as np
import shutil
import webbrowser
from threading import Timer
from flask import send_from_directory


app = Flask(__name__)


SUMMARIES_DIR = "summaries"
os.makedirs(SUMMARIES_DIR, exist_ok=True)

STATIC_WRITE_DIR = os.path.join(os.getcwd(), "generated_files")
os.makedirs(STATIC_WRITE_DIR, exist_ok=True)


# 确保 static 目录存在
os.makedirs("static", exist_ok=True)
HISTORY_FILE = "botcrafter_history.json"
processes = []

HISTORY_FILE_aiminder = "history.json"
RAG_MEMO = "RAG.json"

def retrieve_tfidf(query: str, top_k: int = 5):
    # 1. 加载并切分文档
    loader = TextLoader('sample.txt', encoding='utf-8')
    docs = loader.load()
    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
    chunks = splitter.split_documents(docs)
    corpus = [c.page_content for c in chunks]

    # 2. TF–IDF 向量化
    vectorizer = TfidfVectorizer()
    tfidf_matrix = vectorizer.fit_transform(corpus)  # shape: (n_chunks, n_features)

    q_vec = vectorizer.transform([query])        # shape: (1, n_features)
    scores = (tfidf_matrix @ q_vec.T).toarray().ravel()  # 余弦相似度近似
    top_idxs = np.argsort(scores)[-top_k:][::-1]
    return [chunks[i] for i in top_idxs]

def RAG_memo_load(HISTORY_FILE_aiminder):
    # 如果不存在，创建并写入空数组
    if not os.path.exists(HISTORY_FILE_aiminder):
        with open(HISTORY_FILE_aiminder, "w", encoding="utf-8") as f:
            json.dump([], f)

    # 文件存在时，先检查是否为空
    if os.stat(HISTORY_FILE_aiminder).st_size == 0:
        # 空文件，也写入空数组
        with open(HISTORY_FILE_aiminder, "w", encoding="utf-8") as f:
            json.dump([], f)

    # 现在可以放心读取
    with open(HISTORY_FILE_aiminder, "r", encoding="utf-8") as f:
        return json.load(f)


def load_history_aiminder():
    if os.path.exists(HISTORY_FILE_aiminder):
        with open(HISTORY_FILE_aiminder, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_history_aiminder(history):
    with open(HISTORY_FILE_aiminder, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def aiminder_reply(query):
    retrieved = retrieve_tfidf(query, top_k=5)
    context = "\n\n---\n\n".join([c.page_content for c in retrieved])
    print("找到的上下文：",context)
    full_prompt = f"{RAG_system_prompt}\n\n上下文：\n{context}"

    old_meg = RAG_memo_load(RAG_MEMO)
    reply_text,meg_now = sync_vivogpt_RAG(full_prompt, old_meg, query)
    while reply_text is False and meg_now:
        meg_now.pop(0)
        reply_text = sync_vivogpt_RAG(full_prompt, meg_now, query)
    with open(RAG_MEMO, "w", encoding="utf-8") as f:
        json.dump(meg_now, f, ensure_ascii=False, indent=2)

    return reply_text

def aiminder_sum(query):
    old_meg = RAG_memo_load(RAG_MEMO)
    reply_text,meg_now = sync_vivogpt_RAG(sum_prompt, old_meg, query)
    while reply_text is False and meg_now:
        meg_now.pop(0)
        reply_text = sync_vivogpt_RAG(sum_prompt, meg_now, query)

    return reply_text

def write_openscad_files(directory_path="generated_files", fixed_text="", PA_response=""):
    # 时间戳文件名
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    file_name = f"{timestamp}.scad"
    file_path = os.path.join(directory_path, file_name)

    with open(file_path, "w", encoding="utf-8") as file:
        file.write(fixed_text + "\n" + PA_response)

    return file_path

def open_openscad_files(directory_path="static/result", fixed_text="", PA_response=""):
    openscad_path = r"OpenSCAD\openscad.exe"

    # 确保目录存在
    if not os.path.exists(directory_path):
        os.makedirs(directory_path)

    # 时间戳文件名
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    file_name = f"{timestamp}.scad"
    file_path = os.path.join(directory_path, file_name)

    with open(file_path, "w", encoding="utf-8") as file:
        file.write(fixed_text + "\n" + PA_response)

    # 启动 OpenSCAD
    process = subprocess.Popen([openscad_path, file_path])
    processes.append(process)

    time.sleep(2)

    # 调整窗口
    windows = gw.getWindowsWithTitle(file_name)
    if windows:
        window = windows[0]
        window.maximize()
        return {"status": "success", "message": f"已创建并打开 {file_name}"}
    else:
        return {"status": "error", "message": f"未找到 {file_name} 窗口"}

def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_history(history):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def generate_reply(input_text):
    global TD_response

    all_TD_response = sync_vivogpt(Planner_prompt, input_text)
    TD_response = all_TD_response

    to_remove = ["'''", "openscad", "cpp", "```", "OpenSCAD", "Output:", "output:", "Output :", "output :", "Output: ",
                 "output: ", "scad", "scss"]

    for item in to_remove:
        TD_response = TD_response.replace(item, "")


    return TD_response

def generate_code(input_text_2):
    global PA_response

    all_PA_response = sync_vivogpt(Assembler_prompt, input_text_2)
    PA_response = all_PA_response

    to_remove = ["'''", "openscad", "cpp", "```", "OpenSCAD", "Output:", "output:", "Output :", "output :", "Output: ",
                 "output: ", "scad", "scss"]

    for item in to_remove:
        PA_response = PA_response.replace(item, "")

    return PA_response

def generate_image(fixed, PA_response, filename):
    file_n = write_openscad_files(directory_path="generated_files", fixed_text=fixed, PA_response=PA_response)
    scad_file = file_n
    output_file = filename
    print(scad_file)

    # Command line arguments
    openscad_path = r"OpenSCAD\openscad.exe"
    command = [
        openscad_path,
        "-o", output_file,
        "--imgsize=1920,1080",
        scad_file
    ]

    # Run the command
    try:
        subprocess.run(command, check=True)
        print("图片导出成功！")
    except subprocess.CalledProcessError as e:
        print("导出失败：", e)
        
        
@app.route("/")
def daohang():
    return render_template("AiBotica.html")

@app.route("/index")
def index():
    return render_template("BotCrafter.html")

@app.route("/open3d", methods=["POST"])
def open_3d_file():
    data = request.json
    code = data.get("code", "")

    result = open_openscad_files(
        directory_path="static/result",
        fixed_text=fixed,
        PA_response=code
    )
    return jsonify(result)


@app.route("/chat", methods=["POST"])
def chat():
    data = request.json
    user_input = data.get("message")
    reply_ = generate_reply(user_input)
    reply = sync_vivogpt(translate_prompt, reply_)

    code = generate_code(user_input)
    

    timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
    filename = f"generated_files/image_{timestamp}.png"
    generate_image(fixed,code,filename)
    image_url = "/generated/" + os.path.basename(filename)

    # 保存历史
    history = load_history()
    history.append({"role": "user", "content": user_input})
    assistant_content = {
        "text": reply,
        "code": code,
        "image_url": image_url
    }
    history.append({"role": "assistant", "content": json.dumps(assistant_content, ensure_ascii=False)})
    save_history(history)

    return jsonify({
        "reply": reply,
        "code": code,
        "image_url": image_url
    })


@app.route('/generated/<path:filename>')
def serve_generated(filename):
    return send_from_directory(STATIC_WRITE_DIR, filename)


@app.route("/get_history", methods=["GET"])
def get_history():
    return jsonify(load_history())

@app.route("/indexjinjie")
def indexjinjie():
    return render_template("AiMinder.html")

@app.route("/chataiminder", methods=["POST"])
def chataiminder():
    data = request.json
    user_input = data.get("message")
    reply = aiminder_reply(user_input)
    history = load_history_aiminder()

    history.append({"role": "user", "content": user_input})
    assistant_content = {"text": reply}
    history.append({"role": "assistant", "content": json.dumps(assistant_content, ensure_ascii=False)})
    save_history_aiminder(history)

    return jsonify({"reply": reply})

@app.route("/get_historyaiminder")
def get_history_aiminder():
    return jsonify(load_history_aiminder())


@app.route('/summarize')
def summarize():
    summary_text = aiminder_sum(sum_prompt)

    # 用时间戳命名
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    filename = f"{timestamp}.txt"
    filepath = os.path.join(SUMMARIES_DIR, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(summary_text)

    return jsonify({"summary": summary_text})

@app.route('/get_summaries')
def get_summaries():
    files = sorted(os.listdir(SUMMARIES_DIR))
    summaries = []
    for fname in files:
        fpath = os.path.join(SUMMARIES_DIR, fname)
        with open(fpath, "r", encoding="utf-8") as f:
            summaries.append({
                "filename": fname,
                "content": f.read()
            })
    return jsonify(summaries)


@app.route("/upload", methods=["POST"])
def upload():
    file = request.files.get("file")
    if file:
        fixed_filename = "sample.txt"
        file.save(fixed_filename)
        return jsonify({"message": f"教材 {file.filename} 已保存"})
    else:
        return jsonify({"message": "未接收到教材"}), 400

def open_browser():
    webbrowser.open_new("http://127.0.0.1:5000/")


if __name__ == "__main__":
    Timer(1, open_browser).start()  
    app.run()

