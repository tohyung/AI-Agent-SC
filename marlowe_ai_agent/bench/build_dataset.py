"""Deterministically build versioned cases; do not rerun after a real run."""

from __future__ import annotations

import hashlib
import random
from collections import Counter, defaultdict
from datetime import datetime, timezone

from marlowe_agent.marlowe_ast import ada_to_lovelace

from .cases import Case, save_cases
from .config import DATASET, TYPE_COUNTS
from .templates import build


PERSONAS = ["sinh viên", "chủ tiệm nhỏ", "freelancer", "chủ nhà", "người lớn tuổi",
            "dân văn phòng", "người nước ngoài sống ở Việt Nam", "người kinh doanh online"]
NAMES_VI = ["An", "Bình", "Chi", "Dũng", "Giang", "Hà", "Huy", "Lan", "Minh", "Nga",
            "Phúc", "Quỳnh", "Sơn", "Thảo", "Trang", "Tú", "Uyên", "Vân", "Yến", "Đạt"]
NAMES_EN = ["Alex", "Ben", "Clara", "Daisy", "Evan", "Finn", "Grace", "Helen", "Iris", "Jack",
            "Kate", "Liam", "Maya", "Noah", "Olivia", "Paul", "Rita", "Sam", "Tina", "Will"]
PLACES = ["Huế", "Đà Nẵng", "Hà Nội", "Cần Thơ", "Nha Trang"]
PLACES_EN = ["Hue", "Da Nang", "Hanoi", "Can Tho", "Nha Trang"]
ROLES = {
    "escrow_2party": ["buyer", "seller"], "escrow_3party": ["buyer", "seller", "arbiter"],
    "swap": ["buyer", "seller"], "loan": ["lender", "borrower"],
    "vesting": ["employer", "worker"], "milestone": ["client", "worker"],
    "crowdfunding": ["funder_a", "funder_b", "project"],
    "third_party": ["buyer", "seller", "reporter"],
    "rental_deposit": ["tenant", "landlord"], "cancellation_fee": ["buyer", "seller"],
    "infeasible": [],
}


def _prompt(kind: str, p: dict, lang: str, mode: str, index: int) -> tuple[str, list[dict[str, str]], list[str]]:
    r = defaultdict(str, p["roles"])
    day1 = datetime.fromtimestamp(p["t1"] / 1000, timezone.utc).strftime("%d/%m/%Y")
    day2 = datetime.fromtimestamp(p["t2"] / 1000, timezone.utc).strftime("%d/%m/%Y")
    day3 = datetime.fromtimestamp(p["t3"] / 1000, timezone.utc).strftime("%d/%m/%Y")
    amount = str(p["amount"] // 1000000)
    fee = str(p["fee"] // 1000000)
    if lang == "vi":
        name, place = NAMES_VI[index % 20], PLACES[index // 20]
        prefix = f"{name} ở {place} đây; " + ["em là sinh viên và đang ",
                  "tiệm nhỏ của mình đang ", "mình làm tự do, đang ",
                  "mình là chủ nhà, đang ", "bác muốn nhờ chút, đang ",
                  "tôi làm văn phòng, đang ", "mình mới chuyển tới, đang ",
                  "shop online của mình đang "][index % 8]
        money = f"{amount} ADA"
        deadline = f"ngày {day1}"
        later = f"ngày {day2}" if index % 3 == 0 else "bảy ngày sau hạn đầu"
        final = f"ngày {day3}" if index % 3 == 0 else "mười bốn ngày sau hạn đầu"
        body = {
            "escrow_2party": f"bán chiếc máy ảnh cho {r['buyer']} với giá {{money}}. {r['buyer']} chuyển tiền trước {{deadline}}; nếu họ xác nhận ưng ý trước {{later}} thì {r['seller']} nhận tiền, không thì trả lại {r['buyer']}.",
            "escrow_3party": f"bán món đồ cho {r['buyer']} giá {{money}}. Người này gửi tiền trước {{deadline}}; đến {{later}} nếu có bất đồng thì {r['arbiter']} quyết định chuyển cho {r['seller']} hay hoàn lại {r['buyer']}. Nếu không quyết định thì hoàn lại.",
            "swap": f"muốn đổi {{money}} của {r['buyer']} lấy {p['units']} điểm thưởng GOLD của {r['seller']}. {r['buyer']} đưa phần mình trước {{deadline}}, {r['seller']} đưa điểm trước {{later}}; đủ cả hai mới đổi, thiếu thì mỗi người nhận lại phần của mình.",
            "loan": f"{r['lender']} cho {r['borrower']} vay {{money}} trước {{deadline}}. {r['borrower']} trả cả gốc và thêm {fee} ADA trước {{later}}; nếu không trả thì khoản vay đã đưa đi không tự quay lại.",
            "vesting": f"{r['employer']} dành {{money}} cho {r['worker']}, gửi trước {{deadline}}. Một nửa chuyển cho người làm vào {{later}}, nửa còn lại vào {{final}}.",
            "milestone": f"thuê {r['worker']} làm hai chặng với tổng {{money}}, {r['client']} đưa tiền trước {{deadline}}. Nếu {r['client']} nghiệm thu chặng đầu trước {{later}} thì người làm nhận một nửa; nghiệm thu phần còn lại trước {{final}} thì nhận hết. Phần chưa nghiệm thu phải quay về {r['client']}.",
            "crowdfunding": f"{r['funder_a']} và {r['funder_b']} cùng góp {{money}} cho {r['project']}, mỗi người một nửa. Người đầu góp trước {{deadline}}, người sau trước {{later}}; đủ mức thì dự án nhận, không đủ thì hoàn lại người đã góp.",
            "third_party": f"{r['buyer']} gửi {{money}} trước {{deadline}} để mua hàng từ {r['seller']}. {r['reporter']} báo giá từ 0 đến 100 trước {{later}}; nếu đạt ít nhất {p['threshold']} thì {r['seller']} nhận tiền, thấp hơn thì hoàn cho {r['buyer']}.",
            "rental_deposit": f"{r['tenant']} thuê phòng của {r['landlord']} và đặt cọc {{money}} trước {{deadline}}. Đến {{later}} nếu không hư hại thì hoàn đủ; nếu có hư hại, {r['landlord']} giữ {fee} ADA và trả phần còn lại cho {r['tenant']}.",
            "cancellation_fee": f"{r['buyer']} đặt chuyến đi của {r['seller']} với {{money}} trước {{deadline}}. Trước {{later}} nếu {r['buyer']} hủy thì {r['seller']} giữ phí cố định {fee} ADA, trả phần còn lại; nếu đi thì {r['seller']} nhận tất cả.",
        }
        infeasible = ["muốn tự trừ tiền thuê của khách mỗi tháng mãi mãi dù họ không làm gì thêm.",
                      "muốn nhận trực tiếp tiền mặt VND từ tài khoản ngân hàng mà không ai xác nhận.",
                      "muốn xóa giao dịch đã chốt một cách đơn phương mà không có người tham gia.",
                      "muốn tự sinh thêm lợi nhuận mà không có ai bỏ tiền vào.",
                      "muốn tự biết giá thị trường ngoài đời mà không có ai cung cấp dữ liệu."]
    else:
        name, place = NAMES_EN[index % 20], PLACES_EN[index // 20]
        prefix = f"{name} from {place} here; " + ["I'm a student and am ",
                  "my small shop is ", "I'm a freelancer and am ",
                  "as a homeowner I'm ", "I'm older and am ",
                  "at my office I'm ", "I'm new in town and am ",
                  "my online business is "][index % 8]
        money = f"{amount} ADA"
        deadline = f"{day1}"
        later = f"{day2}" if index % 3 == 0 else "seven days after the first deadline"
        final = f"{day3}" if index % 3 == 0 else "fourteen days after the first deadline"
        body = {
            "escrow_2party": f"selling my camera to {r['buyer']} for {{money}}. {r['buyer']} sends the money by {{deadline}}; if they approve the camera by {{later}}, {r['seller']} receives it; otherwise {r['buyer']} gets it back.",
            "escrow_3party": f"selling an item to {r['buyer']} for {{money}}. They send the money by {{deadline}}; by {{later}} {r['arbiter']} decides whether {r['seller']} receives it or {r['buyer']} gets a refund. No decision means a refund.",
            "swap": f"trading {{money}} from {r['buyer']} for {p['units']} GOLD reward points from {r['seller']}. The first person sends their side by {{deadline}}, the second by {{later}}; exchange only when both arrive, otherwise return what was sent.",
            "loan": f"helping {r['lender']} lend {{money}} to {r['borrower']} by {{deadline}}. {r['borrower']} should return the principal plus {fee} ADA by {{later}}; a missed repayment does not magically reverse the loan.",
            "vesting": f"setting aside {{money}} from {r['employer']} for {r['worker']} by {{deadline}}. Half reaches the worker on {{later}}, and the other half on {{final}}.",
            "milestone": f"hiring {r['worker']} for two pieces of work worth {{money}} total. {r['client']} puts the money in by {{deadline}}; they approve part one by {{later}} and the remainder by {{final}}. Each approval releases half; anything unapproved goes back.",
            "crowdfunding": f"collecting {{money}} for {r['project']} from {r['funder_a']} and {r['funder_b']}, half each. The first contributes by {{deadline}}, the second by {{later}}; the project receives funds only if both do, otherwise contributions return.",
            "third_party": f"buying from {r['seller']} with {{money}} supplied by {r['buyer']} by {{deadline}}. {r['reporter']} reports a price from 0 to 100 by {{later}}; {r['seller']} receives the money if it is at least {p['threshold']}, otherwise {r['buyer']} gets it back.",
            "rental_deposit": f"renting a room from {r['landlord']} to {r['tenant']} with a {{money}} security amount by {{deadline}}. By {{later}} no damage means full refund; damage lets {r['landlord']} keep {fee} ADA and returns the rest.",
            "cancellation_fee": f"booking a trip from {r['seller']} for {r['buyer']} at {{money}} by {{deadline}}. If {r['buyer']} cancels by {{later}}, {r['seller']} keeps a fixed {fee} ADA and returns the rest; completing the trip gives {r['seller']} all of it.",
        }
        infeasible = ["want rent taken automatically every month forever without anyone acting again.",
                      "want cash VND moved straight from a bank account with no one confirming it.",
                      "want a completed arrangement reversed unilaterally with no participant involved.",
                      "want extra profits created without any counterparty providing funds.",
                      "want live real-world prices known without anyone providing the information."]
    if kind == "infeasible":
        intro = f"{name} ở {place} đây; " if lang == "vi" else f"{name} from {place} here; I "
        return intro + infeasible[index % 5], [], []
    hidden: list[dict[str, str]] = []
    missing: list[str] = []
    if mode in {"missing", "ambiguous"}:
        fact = "amount" if index % 2 == 0 or mode == "ambiguous" else "deadline"
        missing.append(fact)
        if fact == "amount":
            hidden.append({"id": fact, "fact": money,
                           "canned_answer": (f"Ý mình là {money}." if lang == "vi" else f"I mean {money}.")})
            if mode == "missing":
                money = "một khoản tiền" if lang == "vi" else "an agreed amount"
            else:
                money += f" (có người ghi {int(amount) + 1} ADA)" if lang == "vi" else f" (another note says {int(amount) + 1} ADA)"
        else:
            hidden.append({"id": fact, "fact": deadline,
                           "canned_answer": (f"Hạn đầu là {deadline}." if lang == "vi" else f"The first deadline is {deadline}.")})
            deadline = "một ngày mình sẽ nói sau" if lang == "vi" else "a date I'll confirm later"
    text = body[kind].format(money=money, deadline=deadline, later=later, final=final)
    if index % 7 == 0:
        text += (" Hôm qua trời mưa nên mình chưa kịp nói chuyện trực tiếp." if lang == "vi"
                 else " We have only talked by phone so far.")
    if index % 11 == 0:
        text += (" Mình hơi lo chuyện phải đòi lại tiền nếu mọi việc không thành." if lang == "vi"
                 else " I'm worried about getting the money back if it does not work out.")
    return prefix + text, hidden, missing


def generate() -> list[Case]:
    rng = random.Random(1234)
    kinds = [kind for kind, count in TYPE_COUNTS.items() for _ in range(count)]
    difficulties = [1] * 25 + [2] * 30 + [3] * 30 + [4] * 15
    language_rest = ["vi"] * (60 - len(TYPE_COUNTS)) + ["en"] * (40 - len(TYPE_COUNTS))
    modes = ["complete"] * 55 + ["missing"] * 30 + ["ambiguous"] * 10
    rng.shuffle(kinds)
    rng.shuffle(difficulties)
    rng.shuffle(language_rest)
    rng.shuffle(modes)
    cases = []
    used = Counter()
    for index, kind in enumerate(kinds):
        lang = "vi" if used[kind] == 0 else ("en" if used[kind] == 1 else language_rest.pop())
        mode = "infeasible" if kind == "infeasible" else modes.pop()
        used[kind] += 1
        role_names = {}
        name_pool = NAMES_VI if lang == "vi" else NAMES_EN
        for n, role_id in enumerate(ROLES[kind]):
            role_names[role_id] = name_pool[(index + n * 3 + 1) % 20]
        day = 3 + index % 18
        t1 = int(datetime(2027, 1, day, 12, tzinfo=timezone.utc).timestamp() * 1000)
        amount_ada = 20 + index * 3
        p = {"roles": role_names, "amount": ada_to_lovelace(amount_ada),
             "fee": ada_to_lovelace(2 + index % 7), "units": 10 + index % 9,
             "threshold": 50, "t1": t1, "t2": t1 + 7 * 86400000, "t3": t1 + 14 * 86400000}
        contract, scenarios = build(kind, p)
        prompt, hidden, missing = _prompt(kind, p, lang, mode, index)
        challenges = (["absolute_date"] if index % 3 == 0 else ["relative_time"])
        if len(role_names) > 2:
            challenges.append("multi_party")
        if kind == "swap":
            challenges.append("non_ada_token")
        if kind in {"vesting", "milestone", "loan"}:
            challenges.append("multi_stage")
        if kind == "third_party":
            challenges.append("third_party_oracle")
        if kind in {"crowdfunding", "third_party"}:
            challenges.append("threshold")
        if kind in {"escrow_2party", "escrow_3party", "swap", "crowdfunding"}:
            challenges.append("refund_on_timeout")
        if mode == "ambiguous":
            challenges.append("conflicting_info")
        if difficulties[index] == 4:
            challenges.append("long_narrative")
        if index % 7 == 0:
            challenges.append("noise_context")
        cases.append(Case(
            id=f"{lang}-{kind}-L{difficulties[index]}-{used[kind]:03d}", version=2,
            type=kind, difficulty=difficulties[index], language=lang, info_mode=mode,
            challenges=challenges, persona=PERSONAS[index % len(PERSONAS)], prompt=prompt,
            params=p, hidden_facts=hidden, missing_facts=missing,
            expected_behavior="should_not_converge_silently" if kind == "infeasible" else "converge",
            reference_contract=contract,
            checks={"structure": [], "timing": [], "scenarios": scenarios},
        ))
    return cases


def main() -> None:
    cases = generate()
    save_cases(cases)
    digest = hashlib.sha256(DATASET.read_bytes()).hexdigest()
    print(f"{len(cases)} cases; dataset_sha256={digest}")


if __name__ == "__main__":
    main()
