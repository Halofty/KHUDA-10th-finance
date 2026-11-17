# vendor를 sys.path에 추가해 open-trading-api 예제 함수를 import
# - 키는 .env(KIS_*)로 관리한다. vendor의 kis_auth.py는 import 시 ~/KIS/config/kis_devlp.yaml만 읽으므로,
#   kis_auth를 import하기 전에 환경변수로 그 yaml을 만들어 둔다 (권한 600, vendor는 고치지 않음)
# - connect(env): real → svr prod, demo → vps 로 ka.auth 후 getTREnv 반환
# - call(env, fn, **kwargs): 호출 제한기 — lock으로 직렬화, 최소 간격 (real 1/15초, demo 0.5초), 토큰 발급은 1분 1회
# - 재시도 규칙 (조회와 주문을 나눈다)
#   조회: EGW00201(초당 호출 초과)이면 잠시 쉬고 재시도
#   주문: 자동 재시도 안 함. 응답이 없으면 접수됐을 수 있으므로 orders.status=unknown으로 두고,
#         당일 주문·체결 조회(종목·매매구분·수량)로 미접수가 확인된 뒤에만 다시 보낸다 (주문번호가 없으므로)
# - 로그 가리기: vendor의 _DEBUG를 켜지 않는다(헤더의 키·토큰을 출력함). 응답을 로그에 남길 때 계좌번호는 가린다
