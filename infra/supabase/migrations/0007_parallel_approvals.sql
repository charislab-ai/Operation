-- CharisLab AI OS — Goal형 병렬 실행: 같은 지시 안에서 여러 부서가 동시에 승인을 기다릴 수 있어
-- 어느 LangGraph interrupt에 대한 승인인지 구분이 필요함
alter table approvals add column interrupt_id text;
