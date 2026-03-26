#!/bin/bash
echo "🛑 Cloud Run 인공지능 서버를 '중지(비공개)' 상태로 전환합니다..."

# 외부(인터넷)에서 누구나 접속할 수 있도록 해주던 권한(allUsers)을 삭제합니다.
gcloud run services remove-iam-policy-binding intern-project \
  --region asia-northeast1 \
  --member="allUsers" \
  --role="roles/run.invoker" \
  --quiet

echo "✅ 서버가 중지되었습니다! 이제 외부 접속자가 들어와도 서버가 켜지지(과금되지) 않습니다."
