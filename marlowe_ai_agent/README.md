# Marlowe AI Agent CLI

Chuong trinh terminal sinh smart contract Marlowe theo chu trinh 3 node:

1. `PromptToDraftNode`: model doc prompt va sinh draft/contract plan/Marlowe AST.
   Neu semantic chua dat, node nay hoi bo sung nguoi dung bang questions/findings tu semantic verification.
   Neu logic graph chua dat, node nay chuyen findings ky thuat thanh cau hoi nghiep vu de nguoi dung tra loi; voi loi thuan AST/JSON, node nay tao phan hoi noi bo de sinh lai draft ma khong bat nguoi dung sua AST.
2. `SemanticVerificationNode`: model tu kiem chung draft voi prompt ve ngu nghia va nghiep vu.
3. `LogicGraphVerificationNode`: dung graph de kiem nhanh cac nhanh hop dong sau khi semantic da pass.

Node 1 va node 2 la LLM-only. Khong con che do offline/heuristic va khong fallback sang validator noi bo cho doc prompt hay semantic verification.

## Cai dat

```powershell
cd C:\Users\Admin\Documents\Codex\2026-08-07\to\outputs\marlowe_ai_agent
python -m pip install -r .\requirements.txt
Copy-Item .\.env.example .\.env
notepad .\.env
```

Vi du `.env` cho OpenRouter:

```text
OPENROUTER_API_KEY=sk-or-v1-key-cua-ban
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_MODEL=nvidia/ten-model-tren-openrouter
LLM_API_STYLE=responses
LLM_TIMEOUT_SECONDS=90
LLM_MAX_TOKENS=8000
LLM_RETRY_ATTEMPTS=3
LLM_RETRY_BASE_DELAY=2
```

## Chay

```powershell
python .\main.py
```

Lenh tren tu dong chay day du:

- tracking node dang chay;
- audit dien giai bang tieng Viet, khong in suy luan tho;
- JSON ket qua cuoi.

Neu chi muon xem tracking/audit va tom tat, khong in JSON day du:

```powershell
python .\main.py --trace-only
```

Flags cu `--trace`, `--audit`, `--narrative-trace` van duoc chap nhan de tuong thich nguoc, nhung tracking/audit da bat mac dinh.

Neu muon tang so vong hoi bo sung:

```powershell
python .\main.py --max-clarifications 6
```

Mac dinh, semantic verification khong pass thi agent hoi bo sung truoc, khong chay xuong logic graph cho toi khi semantic pass.
Neu logic graph khong pass, agent quay lai node 1 de xu ly findings cua logic graph. Node 1 chi hoi nguoi dung khi can them quyet dinh nghiep vu; neu la loi cau truc AST thuan ky thuat, node 1 tu bo sung instruction noi bo de sinh lai draft. Draft moi luon chay lai semantic verification truoc khi quay lai logic graph.

Chi dung co sau khi muon debug:

```powershell
python .\main.py --allow-unverified
```

## Suy luan va ngon ngu

Model duoc yeu cau giao tiep hoan toan bang tieng Viet. Cac truong `reasoning_summary`, `reasoning_narrative`, `findings`, `questions`, `clauses`, `assumptions` deu do model tra ve.

`reasoning_summary` la tom tat ngan. `reasoning_narrative` la lop dien giai trung gian tu nhien hon, bien thien theo prompt va khong theo khuon mau cung. No khong phai chain-of-thought chi tiet.

Ket qua JSON gom:

- `trace`: cac buoc agent da chay.
- `draft.reasoning_summary`: tom tat suy luan cua model o node doc prompt.
- `draft.reasoning_narrative`: dien giai tu nhien cua model o node doc prompt.
- `semantic_verification.reasoning_summary`: tom tat suy luan cua model o node semantic.
- `semantic_verification.reasoning_narrative`: dien giai tu nhien cua model o node semantic.
- `semantic_verification.questions`: cau hoi bo sung do model tu sinh.
- `logic_verification`: ket qua kiem graph sau khi semantic pass.
- `marlowe_contract`: AST Marlowe JSON.
