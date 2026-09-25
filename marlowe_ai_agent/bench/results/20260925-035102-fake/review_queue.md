# Hàng đợi duyệt tay

## vi-milestone-L1-007
Mình là An ở Nha Trang, thuê Giang làm hai chặng với tổng 260 ADA, Bình đưa tiền trước ngày 11/01/2027. Nếu Bình nghiệm thu chặng đầu trước ngày 18/01/2027 thì người làm nhận một nửa; nghiệm thu phần còn lại trước ngày 25/01/2027 thì nhận hết. Phần chưa nghiệm thu phải quay về Bình.

Điểm: 0.3375; đường hội tụ: S+S+L+

Hội thoại:


Mô tả:

1. Before 1799668800000: Bình sends 520000000 ADA base units to Bình; Before 1800273600000: Bình chooses first in [{'from': 1, 'to': 1}]; Pay 260000000 ADA base units from Bình to Giang; Before 1800878400000: Bình chooses finish in [{'from': 1, 'to': 1}]; Pay 260000000 ADA base units from Bình to Giang; Close: remaining balances return to account owners.
2. Before 1799668800000: Bình sends 520000000 ADA base units to Bình; Before 1800273600000: Bình chooses first in [{'from': 1, 'to': 1}]; Pay 260000000 ADA base units from Bình to Giang; At/after 1800878400000: timeout path; Close: remaining balances return to account owners.
3. Before 1799668800000: Bình sends 520000000 ADA base units to Bình; At/after 1800273600000: timeout path; Close: remaining balances return to account owners.
4. At/after 1799668800000: timeout path; Close: remaining balances return to account owners.

Nhận xét người duyệt: ______

## en-swap-L1-004
I'm Tina living in Hue, trading 74 ADA from Will for 10 GOLD reward points from Clara. The first person sends their side by 03/01/2027, the second by 10/01/2027; exchange only when both arrive, otherwise return what was sent.

Điểm: 0.5; đường hội tụ: S+S+L+

Hội thoại:


Mô tả:

1. Before 1798977600000: Will sends 148000000 ADA base units to Will; Before 1799582400000: Clara sends 20 GOLD to Clara; Pay 148000000 ADA base units from Will to Clara; Pay 20 GOLD from Clara to Will; Close: remaining balances return to account owners.
2. Before 1798977600000: Will sends 148000000 ADA base units to Will; At/after 1799582400000: timeout path; Close: remaining balances return to account owners.
3. At/after 1798977600000: timeout path; Close: remaining balances return to account owners.

Nhận xét người duyệt: ______

## vi-crowdfunding-L1-007
Mình là Quỳnh ở Cần Thơ, Sơn và Tú cùng góp 233 ADA cho Yến, mỗi người một nửa. Người đầu góp trước ngày 20/01/2027, người sau trước ngày 27/01/2027; đủ mức thì dự án nhận, không đủ thì hoàn lại người đã góp.

Điểm: 0.31666666666666665; đường hội tụ: S+S+L+

Hội thoại:


Mô tả:

1. Before 1800446400000: Sơn sends 233000000 ADA base units to Sơn; Before 1801051200000: Tú sends 233000000 ADA base units to Tú; Pay 233000000 ADA base units from Sơn to Yến; Pay 233000000 ADA base units from Tú to Yến; Close: remaining balances return to account owners.
2. Before 1800446400000: Sơn sends 233000000 ADA base units to Sơn; At/after 1801051200000: timeout path; Close: remaining balances return to account owners.
3. At/after 1800446400000: timeout path; Close: remaining balances return to account owners.

Nhận xét người duyệt: ______

## en-escrow_3party-L3-003
I'm Grace living in Da Nang, selling an item to Helen for an agreed amount. They send the money by 11/01/2027; by 18/01/2027 Noah decides whether Kate receives it or Helen gets a refund. No decision means a refund.

Điểm: 0.31666666666666665; đường hội tụ: S+S+L+

Hội thoại:


Mô tả:

1. Before 1799668800000: Helen sends 196000000 ADA base units to Helen; Before 1800273600000: Noah chooses release in [{'from': 1, 'to': 1}]; Pay 196000000 ADA base units from Helen to Kate; Close: remaining balances return to account owners.
2. Before 1799668800000: Helen sends 196000000 ADA base units to Helen; Before 1800273600000: Noah chooses refund in [{'from': 0, 'to': 0}]; Pay 196000000 ADA base units from Helen to Helen; Close: remaining balances return to account owners.
3. Before 1799668800000: Helen sends 196000000 ADA base units to Helen; At/after 1800273600000: timeout path; Pay 196000000 ADA base units from Helen to Helen; Close: remaining balances return to account owners.
4. At/after 1799668800000: timeout path; Close: remaining balances return to account owners.

Nhận xét người duyệt: ______

## vi-cancellation_fee-L3-005
Mình là Quỳnh ở Hà Nội, Sơn đặt chuyến đi của Tú với 173 ADA (có người ghi 174 ADA) trước ngày 18/01/2027. Trước ngày 25/01/2027 nếu Sơn hủy thì Tú giữ phí cố định 4 ADA, trả phần còn lại; nếu đi thì Tú nhận tất cả.

Điểm: 0.25; đường hội tụ: S+S+L+

Hội thoại:


Mô tả:

1. Before 1800273600000: Sơn sends 346000000 ADA base units to Sơn; Before 1800878400000: Sơn chooses cancel in [{'from': 0, 'to': 0}]; Pay 8000000 ADA base units from Sơn to Tú; Pay 338000000 ADA base units from Sơn to Sơn; Close: remaining balances return to account owners.
2. Before 1800273600000: Sơn sends 346000000 ADA base units to Sơn; Before 1800878400000: Sơn chooses complete in [{'from': 1, 'to': 1}]; Pay 346000000 ADA base units from Sơn to Tú; Close: remaining balances return to account owners.
3. Before 1800273600000: Sơn sends 346000000 ADA base units to Sơn; At/after 1800878400000: timeout path; Close: remaining balances return to account owners.
4. At/after 1800273600000: timeout path; Close: remaining balances return to account owners.

Nhận xét người duyệt: ______

## vi-escrow_3party-L4-006
Mình là Trang ở Hà Nội, bán món đồ cho Tú giá 182 ADA. Người này gửi tiền trước ngày 03/01/2027; đến ngày 10/01/2027 nếu có bất đồng thì Bình quyết định chuyển cho Yến hay hoàn lại Tú. Nếu không quyết định thì hoàn lại.

Điểm: 0.31666666666666665; đường hội tụ: S+S+L+

Hội thoại:


Mô tả:

1. Before 1798977600000: Tú sends 364000000 ADA base units to Tú; Before 1799582400000: Bình chooses release in [{'from': 1, 'to': 1}]; Pay 364000000 ADA base units from Tú to Yến; Close: remaining balances return to account owners.
2. Before 1798977600000: Tú sends 364000000 ADA base units to Tú; Before 1799582400000: Bình chooses refund in [{'from': 0, 'to': 0}]; Pay 364000000 ADA base units from Tú to Tú; Close: remaining balances return to account owners.
3. Before 1798977600000: Tú sends 364000000 ADA base units to Tú; At/after 1799582400000: timeout path; Pay 364000000 ADA base units from Tú to Tú; Close: remaining balances return to account owners.
4. At/after 1798977600000: timeout path; Close: remaining balances return to account owners.

Nhận xét người duyệt: ______

## en-crowdfunding-L2-002
I'm Finn living in Da Nang, collecting 95 ADA for Maya from Grace and Jack, half each. The first contributes by 10/01/2027, the second by 17/01/2027; the project receives funds only if both do, otherwise contributions return.

Điểm: 0.31666666666666665; đường hội tụ: S+S+L+

Hội thoại:


Mô tả:

1. Before 1799582400000: Grace sends 95000000 ADA base units to Grace; Before 1800187200000: Jack sends 95000000 ADA base units to Jack; Pay 95000000 ADA base units from Grace to Maya; Pay 95000000 ADA base units from Jack to Maya; Close: remaining balances return to account owners.
2. Before 1799582400000: Grace sends 95000000 ADA base units to Grace; At/after 1800187200000: timeout path; Close: remaining balances return to account owners.
3. At/after 1799582400000: timeout path; Close: remaining balances return to account owners.

Nhận xét người duyệt: ______

## vi-milestone-L1-007
Mình là An ở Nha Trang, thuê Giang làm hai chặng với tổng 260 ADA, Bình đưa tiền trước ngày 11/01/2027. Nếu Bình nghiệm thu chặng đầu trước ngày 18/01/2027 thì người làm nhận một nửa; nghiệm thu phần còn lại trước ngày 25/01/2027 thì nhận hết. Phần chưa nghiệm thu phải quay về Bình.

Điểm: 0.3375; đường hội tụ: S+S+L+

Hội thoại:


Mô tả:

1. Before 1799668800000: Bình sends 520000000 ADA base units to Bình; Before 1800273600000: Bình chooses first in [{'from': 1, 'to': 1}]; Pay 260000000 ADA base units from Bình to Giang; Before 1800878400000: Bình chooses finish in [{'from': 1, 'to': 1}]; Pay 260000000 ADA base units from Bình to Giang; Close: remaining balances return to account owners.
2. Before 1799668800000: Bình sends 520000000 ADA base units to Bình; Before 1800273600000: Bình chooses first in [{'from': 1, 'to': 1}]; Pay 260000000 ADA base units from Bình to Giang; At/after 1800878400000: timeout path; Close: remaining balances return to account owners.
3. Before 1799668800000: Bình sends 520000000 ADA base units to Bình; At/after 1800273600000: timeout path; Close: remaining balances return to account owners.
4. At/after 1799668800000: timeout path; Close: remaining balances return to account owners.

Nhận xét người duyệt: ______

## vi-rental_deposit-L1-007
Mình là Giang ở Nha Trang, Hà thuê phòng của Minh và đặt cọc một khoản tiền trước ngày 15/01/2027. Đến ngày 22/01/2027 nếu không hư hại thì hoàn đủ; nếu có hư hại, Minh giữ 2 ADA và trả phần còn lại cho Hà.

Điểm: 0.25; đường hội tụ: S+S+L+

Hội thoại:


Mô tả:

1. Before 1800014400000: Hà sends 544000000 ADA base units to Hà; Before 1800619200000: Minh chooses damage in [{'from': 0, 'to': 0}]; Pay 544000000 ADA base units from Hà to Hà; Close: remaining balances return to account owners.
2. Before 1800014400000: Hà sends 544000000 ADA base units to Hà; Before 1800619200000: Minh chooses damage in [{'from': 1, 'to': 1}]; Pay 4000000 ADA base units from Hà to Minh; Pay 540000000 ADA base units from Hà to Hà; Close: remaining balances return to account owners.
3. Before 1800014400000: Hà sends 544000000 ADA base units to Hà; At/after 1800619200000: timeout path; Close: remaining balances return to account owners.
4. At/after 1800014400000: timeout path; Close: remaining balances return to account owners.

Nhận xét người duyệt: ______

## vi-vesting-L1-004
Mình là Dũng ở Đà Nẵng, Giang dành 89 ADA cho Lan, gửi trước ngày 08/01/2027. Một nửa chuyển cho người làm vào ngày 15/01/2027, nửa còn lại vào ngày 22/01/2027.

Điểm: 0.3375; đường hội tụ: S+S+L+

Hội thoại:


Mô tả:

1. Before 1799409600000: Giang sends 178000000 ADA base units to Giang; At/after 1800014400000: timeout path; Pay 89000000 ADA base units from Giang to Lan; At/after 1800619200000: timeout path; Pay 89000000 ADA base units from Giang to Lan; Close: remaining balances return to account owners.
2. At/after 1799409600000: timeout path; Close: remaining balances return to account owners.

Nhận xét người duyệt: ______
