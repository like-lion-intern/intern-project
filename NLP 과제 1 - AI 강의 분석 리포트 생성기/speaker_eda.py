import os
import re
import pandas as pd
from collections import Counter
import glob

def extract_speakers_to_csv(folder_path, output_csv="speaker_eda_result.csv"):
    """
    지정된 폴더 내의 모든 txt 파일을 읽어 화자 ID와 발화 횟수를 CSV로 추출합니다.
    """
    # 1. 분석할 파일 목록 가져오기
    file_pattern = os.path.join(folder_path, "*.txt")
    txt_files = glob.glob(file_pattern)
    
    if not txt_files:
        print(f"경고: '{folder_path}' 폴더에 txt 파일이 없습니다.")
        return
    
    print(f"총 {len(txt_files)}개의 파일을 분석합니다...")
    
    # 패턴 설명: <시간> 화자ID: (예: <09:11:04> b8c55a6e: 또는 <09:11:04> 학생_1:)
    # 이전보다 더 넓은 범위의 화자 ID(한글, 공백, 특수문자 포함)를 커버하도록 수정
    speaker_pattern = re.compile(r'<[0-9]{2}:[0-9]{2}:[0-9]{2}>\s+(.+?):')
    
    # 파일별 데이터를 담을 리스트
    all_records = []
    
    # 3. 각 파일 순회하며 화자 추출
    for file_path in txt_files:
        file_name = os.path.basename(file_path)
        speakers_in_file = []
        # 한글 깨짐 방지를 위해 인코딩 명시 (에러 발생 시 'cp949'로 변경)
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                # 대용량 파일을 고려하여 한 줄씩 읽어 메모리 효율성 개선
                for line in f:
                    # 정규식으로 매칭된 모든 화자 ID 리스트 추출
                    matches = speaker_pattern.findall(line)
                    speakers_in_file.extend(matches)
            
            # 파일별 화자 빈도수 카운트
            counts = Counter(speakers_in_file)
            for speaker_id, count in counts.items():
                all_records.append({
                    'File_Name': file_name,
                    'Speaker_ID': speaker_id,
                    'Utterance_Count': count
                })
        except Exception as e:
            print(f"파일 읽기 오류 ({file_name}): {e}")

    # 4. 리스트를 Pandas DataFrame으로 변환
    df = pd.DataFrame(all_records)
    
    if df.empty:
        print("경고: 추출된 화자 데이터가 없습니다.")
        return

    # 5. 파일명 및 발화 횟수 기준 정렬 (파일명 오름차순, 발화수 내림차순)
    df = df.sort_values(by=['File_Name', 'Utterance_Count'], ascending=[True, False]).reset_index(drop=True)
    
    # 6. CSV 파일로 저장
    df.to_csv(output_csv, index=False, encoding='utf-8-sig') # utf-8-sig는 엑셀 한글 깨짐 방지
    
    print("="*50)
    print(f"분석 완료! 결과가 '{output_csv}'에 저장되었습니다.")
    print("="*50)
    print("분석 결과 샘플 (Top 10):")
    print(df.head(10))


if __name__ == "__main__":
    # ========== 실행 부분 ==========
    # 실제 txt 파일들이 모여있는 폴더 경로로 변경해주세요. (예: './data/stt_files')
    DATA_FOLDER_PATH = r"c:\Users\changhyun\Desktop\likelion_internship\NLP 과제 1 - AI 강의 분석 리포트 생성기\강의 스크립트" 
    extract_speakers_to_csv(DATA_FOLDER_PATH, "speaker_eda_result.csv")