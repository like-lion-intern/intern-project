import os
import glob
from collections import defaultdict

def preprocess_lecture_transcripts(input_dir, output_dir, main_speaker_ratio_threshold=0.05):
    """
    강의 트랜스크립트 텍스트 파일을 전처리(1, 2단계)합니다.

    1. 각 파일별 화자들의 발화 횟수(Utterance)를 계산합니다.
    2. 전체 발화량 대비 특정 비율(기본 5%) 미만인 화자는 노이즈/보조강사로 간주하여 필터링합니다.
    3. 남은 메인 화자(들)의 발화 텍스트만 시간순으로 추출하여 화자 태그 없이 텍스트만 저장합니다. (줄바꿈 유지)

    Args:
        input_dir (str): 원본 txt 파일들이 있는 디렉토리 경로
        output_dir (str): 전처리 완료된 txt 파일을 저장할 디렉토리 경로
        main_speaker_ratio_threshold (float): 메인 화자로 간주할 최소 발화량 비율 (기본 0.05 = 5%)
    """
    
    # 출력 폴더가 없으면 생성
    os.makedirs(output_dir, exist_ok=True)
    
    # 텍스트 파일 목록 가져오기
    file_pattern = os.path.join(input_dir, "*.txt")
    txt_files = glob.glob(file_pattern)
    
    if not txt_files:
        print(f"[{input_dir}] 경로에 처리할 .txt 파일이 없습니다.")
        return
        
    print(f"총 {len(txt_files)}개의 파일 전처리를 시작합니다...")
    
    for file_path in txt_files:
        filename = os.path.basename(file_path)
        
        # 1. 문서 스캔 및 화자별 발화 빈도 카운팅
        speaker_counts = defaultdict(int)
        lines_data = [] # (원문 라인, 화자 ID, 실제 텍스트)를 튜플로 순서대로 저장
        
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                
                import re
                
                # 1. 타임스탬프 류(`<hh:mm:ss>`)가 라인 맨 앞에 있으면 제거
                line = re.sub(r'^<\d{2}:\d{2}:\d{2}>\s*', '', line)
                
                # 2. 첫 번째로 등장하는 8자리 헥사 문자열(화자 ID)과 그 뒤의 콜론(:) 또는 공백을 찾아 분리
                match = re.match(r'^\[?([a-f0-9]{8})\]?:?\s*(.*)', line)
                
                if match:
                    speaker_id = match.group(1)
                    text = match.group(2).strip()
                    
                    if text.startswith(':'):
                        text = text[1:].strip()
                
                    speaker_counts[speaker_id] += 1
                    lines_data.append((line, speaker_id, text))
                else:
                    # 화자 구분자가 없는 특이 라인은 텍스트만 보존 (선택사항)
                    lines_data.append((line, "UNKNOWN", line))
        
        # 전체 발화 건수 합계
        total_utterances = sum(speaker_counts.values())
        if total_utterances == 0:
            print(f"[{filename}] 화자 분리 형식이 아니거나 발화 내용이 없습니다.")
            continue
            
        # 2. 메인 강사 판별 (전체 발화량 대비 특정 비율 이상인 화자들 추출)
        main_speakers = set()
        for spk, count in speaker_counts.items():
            ratio = count / total_utterances
            if ratio >= main_speaker_ratio_threshold:
                main_speakers.add(spk)
                
        # 판별된 메인 강사가 한 명도 없으면 가장 발화 많은 화자 1명만 선택
        if not main_speakers:
            top_speaker = sorted(speaker_counts.items(), key=lambda x: x[1], reverse=True)[0][0]
            main_speakers.add(top_speaker)
            
        # 3. 메인 화자의 텍스트만 모아 하나로 이어붙이기
        processed_texts = []
        for orig_line, spk_id, text in lines_data:
            if spk_id in main_speakers:
                 processed_texts.append(text)
        
        # 👉 [수정된 부분] 문장별 구분을 유지하기 위해 줄바꿈(\n)으로 join 합니다.
        final_script = "\n".join(processed_texts)
        
        # 전처리된 텍스트 저장
        output_path = os.path.join(output_dir, filename)
        with open(output_path, 'w', encoding='utf-8') as out_f:
            out_f.write(final_script)
            
        print(f"✅ [{filename}] 처리 완료 (총 발화: {total_utterances}건 -> 보존 화자 수: {len(main_speakers)}명)")

if __name__ == "__main__":
    # =============== 사용 설정 ===============
    INPUT_FOLDER = r"c:\Users\changhyun\Desktop\likelion_internship\NLP 과제 1 - AI 강의 분석 리포트 생성기\강의 스크립트" 
    OUTPUT_FOLDER = r"c:\Users\changhyun\Desktop\likelion_internship\NLP 과제 1 - AI 강의 분석 리포트 생성기\강의 스크립트_1차_전처리완료"
    THRESHOLD_RATIO = 0.05
    # ==========================================
    
    preprocess_lecture_transcripts(INPUT_FOLDER, OUTPUT_FOLDER, THRESHOLD_RATIO)
    print("\n🎉 모든 파일 전처리 작업이 완료되었습니다!")