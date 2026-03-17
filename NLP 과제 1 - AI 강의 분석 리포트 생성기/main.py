# main.py

import os
import json
import google.generativeai as genai
from openai import OpenAI
from dotenv import load_dotenv

# 사용자 정의 모듈 (prompts.py)에서 프롬프트 생성 함수 불러오기
from prompts import get_instructor_feedback_prompt

def setup_gemini():
    """환경 변수에서 API 키를 불러와 Gemini 설정을 초기화해."""
    # .env 파일 로드
    load_dotenv()
    
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError(".env 파일에 GEMINI_API_KEY가 제대로 설정되지 않았어.")
        
    genai.configure(api_key=api_key)
    
    # 처음에 말했던 대로 Lite 모델을 쓰고 싶다면 'gemini-3.1-flash-lite'로 바꿔도 좋아!
    return genai.GenerativeModel('gemini-1.5-flash')
class GPTWrapper:
    """Gemini의 generate_content 인터페이스를 GPT에서도 똑같이 쓰기 위한 래퍼 클래스야."""
    def __init__(self, client, model_name="gpt-4o"):
        self.client = client
        self.model_name = model_name
        
    def generate_content(self, prompt):
        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7
        )
        class MockResponse:
            def __init__(self, text):
                self.text = text
        return MockResponse(response.choices[0].message.content)

def setup_gpt():
    """환경 변수에서 API 키를 불러와 GPT 설정을 초기화해."""
    # .env 파일 로드
    load_dotenv()
    
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError(".env 파일에 OPENAI_API_KEY가 제대로 설정되지 않았어.")
        
    client = OpenAI(api_key=api_key)
    return GPTWrapper(client)

def load_json_data(filepath):
    """JSON 파일을 읽어서 모델이 이해하기 쉬운 문자열로 변환해 반환해."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
        return json.dumps(raw_data, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"데이터 로드 실패: {e}")
        return None

def main():
    INPUT_JSON = "data.json"
    OUTPUT_REPORT = "instructor_feedback_report.md"

    # 1. 테스트용 임시 JSON 파일 생성 (실제 네 데이터가 있다면 이 부분은 지워도 돼)
    if not os.path.exists(INPUT_JSON):
        print(f"'{INPUT_JSON}' 파일이 없어서 테스트용 데이터를 임시로 만들게.")
        sample_data = {
            "lecture_info": {"title": "데이터 분석 기초", "date": "2026-03-17"},
            "stt_analysis": {"speech_rate_wpm": 130, "clarity_score": 92},
            "checklist_scores": {"student_engagement": 85, "concept_clarity": 88}
        }
        with open(INPUT_JSON, 'w', encoding='utf-8') as f:
            json.dump(sample_data, f, ensure_ascii=False, indent=2)

    # 2. 데이터 불러오기
    data_str = load_json_data(INPUT_JSON)
    if not data_str:
        return

    # 3. 모델 초기화 및 프롬프트 준비
    try:
        # GPT 모델로 테스트하고 싶다면 아래 줄을 model = setup_gpt() 로 변경해!
        model = setup_gemini()
        prompt = get_instructor_feedback_prompt(data_str)
    except Exception as e:
        print(f"설정 오류: {e}")
        return

    # 4. 리포트 생성 요청
    print("강의 피드백 리포트를 생성하는 중이야. 잠시만 기다려줘...")
    try:
        response = model.generate_content(prompt)
        
        # 5. 결과 저장
        with open(OUTPUT_REPORT, 'w', encoding='utf-8') as f:
            f.write(response.text)
        print(f"✨ 완료! 리포트가 '{OUTPUT_REPORT}'에 성공적으로 저장되었어.")
        
    except Exception as e:
        print(f"API 호출 중 오류 발생: {e}")

if __name__ == "__main__":
    main()