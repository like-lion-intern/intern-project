import os
import sys
import time
import math
from pathlib import Path
from dotenv import load_dotenv

# 상위 폴더(src, scripts) 모듈을 가져오기 위한 경로 추가
sys.path.append(str(Path(__file__).parent.parent))

from scripts.run_pipeline import Embedder, parse_stt_file, semantic_chunking

# 1. 환경 변수 로드
load_dotenv()

# OpenAI 라이브러리 검사
try:
    import openai
except ImportError:
    print("❌ openai 라이브러리가 없습니다. 'pip install openai'를 실행하세요.")
    sys.exit(1)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("CHAT_GPT_API")
if not OPENAI_API_KEY:
    print("❌ .env 파일에 OPENAI_API_KEY(또는 CHAT_GPT_API)가 설정되어 있지 않습니다!")
    sys.exit(1)

def cosine_similarity(v1, v2):
    dot = sum(x*y for x, y in zip(v1, v2))
    norm_a = math.sqrt(sum(x*x for x in v1))
    norm_b = math.sqrt(sum(y*y for y in v2))
    return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0

def measure_similarity_stats(embeddings):
    """연속된 문장들 간의 평균 코사인 유사도를 계산하여 임계값 민감도 파악"""
    if len(embeddings) < 2:
        return 0, 0, 0
    sims = [cosine_similarity(embeddings[i], embeddings[i+1]) for i in range(len(embeddings)-1)]
    return min(sims), sum(sims)/len(sims), max(sims)

def run_benchmark():
    target_file = Path("stt_log_removed/2026-02-12.txt")
    if not target_file.exists():
        print(f"❌ {target_file} 파일을 찾을 수 없습니다.")
        return

    print(f"\n📂 데이터 로드 중: {target_file}")
    utterances_raw = parse_stt_file(target_file)
    utterances = [u for u in utterances_raw if str(u.get("text", "")).strip()]
    texts = [u.get("text", "") for u in utterances]
    print(f"✅ 총 문장 개수: {len(texts)}개 (원본 {len(utterances_raw)}개)")

    total_characters = sum(len(t) for t in texts)
    # 대략적인 토큰 수 (문자 수의 1/2로 가정, 한국어)
    estimated_tokens = total_characters

    # ==========================================
    # 1. Local (multilingual-e5-small) 벤치마크
    # ==========================================
    print("\n" + "="*50)
    print("🚀 [TEST 1] 로컬 모델 (multilingual-e5-small)")
    print("="*50)
    start_time = time.time()
    local_embedder = Embedder(model_id="intfloat/multilingual-e5-small", device="cpu")
    local_embeddings = local_embedder.encode(texts)
    local_time = time.time() - start_time

    min_sim, avg_sim, max_sim = measure_similarity_stats(local_embeddings)
    
    # 0.74 로 자를 때의 청크 결과
    segment_rows = [{"start_idx": 0, "end_idx": len(utterances) - 1, "segment_id": "test", "label": "test"}]
    local_chunks = semantic_chunking(segment_rows, utterances, local_embeddings, sim_threshold=0.74)
    
    print(f"⏱️ 걸린 시간: {local_time:.2f} 초")
    print(f"📊 유사도 스펙트럼 (인접문장): 최소 {min_sim:.3f} | 평균 {avg_sim:.3f} | 최대 {max_sim:.3f}")
    if avg_sim < 0.74:
        print(f"⚠️ [경고] 평균 유사도({avg_sim:.3f})가 임계값(0.74)보다 낮음. 문장이 너무 파편화될 가능성 높음.")
    print(f"📦 생성된 청크 개수 (threshold=0.74 기준): {len(local_chunks)}개")


    # ==========================================
    # 2. API (text-embedding-ada-002) 벤치마크
    # ==========================================
    print("\n" + "="*50)
    print("🚀 [TEST 2] 클라우드 API (text-embedding-ada-002)")
    print("="*50)
    client = openai.OpenAI(api_key=OPENAI_API_KEY)
    
    start_time = time.time()
    # ada-002는 최대 2048개의 텍스트 배열을 한번에 요청 가능
    response = client.embeddings.create(
        input=texts,
        model="text-embedding-ada-002"
    )
    api_embeddings = [data.embedding for data in response.data]
    api_time = time.time() - start_time
    total_tokens = response.usage.total_tokens

    min_sim_api, avg_sim_api, max_sim_api = measure_similarity_stats(api_embeddings)
    
    # OpenAI의 임계값 최적화
    best_threshold = avg_sim_api - 0.05
    api_chunks = semantic_chunking(segment_rows, utterances, api_embeddings, sim_threshold=best_threshold)

    # 파편화를 막기위해 기존 0.74를 쓸 때의 개수
    bad_api_chunks = semantic_chunking(segment_rows, utterances, api_embeddings, sim_threshold=0.74)

    print(f"⏱️ 걸린 시간: {api_time:.2f} 초")
    print(f"💸 소모된 토큰: {total_tokens} tokens (예상 과금: ${total_tokens * 0.0001 / 1000:.5f})")
    print(f"📊 유사도 스펙트럼 (인접문장): 최소 {min_sim_api:.3f} | 평균 {avg_sim_api:.3f} | 최대 {max_sim_api:.3f}")
    
    print("\n💡 [임계값(Threshold) 비교 분석]")
    print(f"👉 로컬과 동일하게 0.74를 적용할 경우 청크 개수: {len(bad_api_chunks)}개")
    if avg_sim_api > 0.8:
        print("  => (분석) OpenAI는 벡터가 0.8 이상으로 매우 촘촘합니다. 0.74를 쓰면 '전체가 거의 비슷하다'고 판단해 너무 적은 청크로 묶일 위험이 큽니다.")
    print(f"👉 OpenAI 최적 임계값({best_threshold:.3f}) 적용 시 청크 개수: {len(api_chunks)}개")
    
    # 결과를 파일로 저장
    with open("tests/benchmark_output.txt", "w") as f:
        f.write(f"local_time: {local_time}\n")
        f.write(f"local_chunks: {len(local_chunks)}\n")
        f.write(f"api_time: {api_time}\n")
        f.write(f"api_chunks: {len(api_chunks)}\n")
        f.write(f"api_cost: {total_tokens * 0.0001 / 1000}\n")
        f.write(f"local_sim: {min_sim},{avg_sim},{max_sim}\n")
        f.write(f"api_sim: {min_sim_api},{avg_sim_api},{max_sim_api}\n")

if __name__ == "__main__":
    run_benchmark()
