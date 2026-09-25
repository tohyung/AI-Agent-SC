# Hàng đợi duyệt tay

## vi-escrow_3party-L4-006
Trang ở Hà Nội đây; mình mới chuyển tới, đang bán món đồ cho Tú giá 182 ADA. Người này gửi tiền trước ngày 03/01/2027; đến ngày 10/01/2027 nếu có bất đồng thì Bình quyết định chuyển cho Yến hay hoàn lại Tú. Nếu không quyết định thì hoàn lại.

Điểm: 1.0; đường hội tụ: S+S+L+

Hội thoại:


Mô tả:

1. Before 1798977600000: Tú sends 182000000 ADA base units to Tú; Before 1799582400000: Bình chooses release in [{'from': 1, 'to': 1}]; Pay 182000000 ADA base units from Tú to Yến; Close: remaining balances return to account owners.
2. Before 1798977600000: Tú sends 182000000 ADA base units to Tú; Before 1799582400000: Bình chooses refund in [{'from': 0, 'to': 0}]; Pay 182000000 ADA base units from Tú to Tú; Close: remaining balances return to account owners.
3. Before 1798977600000: Tú sends 182000000 ADA base units to Tú; At/after 1799582400000: timeout path; Pay 182000000 ADA base units from Tú to Tú; Close: remaining balances return to account owners.
4. At/after 1798977600000: timeout path; Close: remaining balances return to account owners.

Nhận xét người duyệt: ______

## en-crowdfunding-L2-002
Finn from Da Nang here; my small shop is collecting 95 ADA for Maya from Grace and Jack, half each. The first contributes by 10/01/2027, the second by seven days after the first deadline; the project receives funds only if both do, otherwise contributions return.

Điểm: 1.0; đường hội tụ: S+S+L+

Hội thoại:


Mô tả:

1. Before 1799582400000: Grace sends 47500000 ADA base units to Grace; Before 1800187200000: Jack sends 47500000 ADA base units to Jack; Pay 47500000 ADA base units from Grace to Maya; Pay 47500000 ADA base units from Jack to Maya; Close: remaining balances return to account owners.
2. Before 1799582400000: Grace sends 47500000 ADA base units to Grace; At/after 1800187200000: timeout path; Close: remaining balances return to account owners.
3. At/after 1799582400000: timeout path; Close: remaining balances return to account owners.

Nhận xét người duyệt: ______

## en-swap-L1-004
Tina from Hue here; I'm a freelancer and am trading 74 ADA from Will for 10 GOLD reward points from Clara. The first person sends their side by 03/01/2027, the second by 10/01/2027; exchange only when both arrive, otherwise return what was sent.

Điểm: 1.0; đường hội tụ: S+S+L+

Hội thoại:


Mô tả:

1. Before 1798977600000: Will sends 74000000 ADA base units to Will; Before 1799582400000: Clara sends 10 GOLD to Clara; Pay 74000000 ADA base units from Will to Clara; Pay 10 GOLD from Clara to Will; Close: remaining balances return to account owners.
2. Before 1798977600000: Will sends 74000000 ADA base units to Will; At/after 1799582400000: timeout path; Close: remaining balances return to account owners.
3. At/after 1798977600000: timeout path; Close: remaining balances return to account owners.

Nhận xét người duyệt: ______

## vi-rental_deposit-L1-007
Giang ở Nha Trang đây; bác muốn nhờ chút, đang Hà thuê phòng của Minh và đặt cọc một khoản tiền trước ngày 15/01/2027. Đến ngày 22/01/2027 nếu không hư hại thì hoàn đủ; nếu có hư hại, Minh giữ 2 ADA và trả phần còn lại cho Hà. Hôm qua trời mưa nên mình chưa kịp nói chuyện trực tiếp.

Điểm: 1.0; đường hội tụ: S+S+L+

Hội thoại:


Mô tả:

1. Before 1800014400000: Hà sends 272000000 ADA base units to Hà; Before 1800619200000: Minh chooses damage in [{'from': 0, 'to': 0}]; Pay 272000000 ADA base units from Hà to Hà; Close: remaining balances return to account owners.
2. Before 1800014400000: Hà sends 272000000 ADA base units to Hà; Before 1800619200000: Minh chooses damage in [{'from': 1, 'to': 1}]; Pay 2000000 ADA base units from Hà to Minh; Pay 270000000 ADA base units from Hà to Hà; Close: remaining balances return to account owners.
3. Before 1800014400000: Hà sends 272000000 ADA base units to Hà; At/after 1800619200000: timeout path; Close: remaining balances return to account owners.
4. At/after 1800014400000: timeout path; Close: remaining balances return to account owners.

Nhận xét người duyệt: ______

## vi-escrow_2party-L4-013
Tú ở Nha Trang đây; shop online của mình đang bán chiếc máy ảnh cho Uyên với giá 305 ADA. Uyên chuyển tiền trước một ngày mình sẽ nói sau; nếu họ xác nhận ưng ý trước bảy ngày sau hạn đầu thì Đạt nhận tiền, không thì trả lại Uyên.

Điểm: 1.0; đường hội tụ: S+S+L+

Hội thoại:


Mô tả:

1. Before 1799409600000: Uyên sends 305000000 ADA base units to Uyên; Before 1800014400000: Uyên chooses approve in [{'from': 1, 'to': 1}]; Pay 305000000 ADA base units from Uyên to Đạt; Close: remaining balances return to account owners.
2. Before 1799409600000: Uyên sends 305000000 ADA base units to Uyên; Before 1800014400000: Uyên chooses reject in [{'from': 0, 'to': 0}]; Pay 305000000 ADA base units from Uyên to Uyên; Close: remaining balances return to account owners.
3. Before 1799409600000: Uyên sends 305000000 ADA base units to Uyên; At/after 1800014400000: timeout path; Pay 305000000 ADA base units from Uyên to Uyên; Close: remaining balances return to account owners.
4. At/after 1799409600000: timeout path; Close: remaining balances return to account owners.

Nhận xét người duyệt: ______
