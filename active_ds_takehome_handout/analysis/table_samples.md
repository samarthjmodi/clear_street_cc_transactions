# Source table samples
First 10 records in file order; finance assumptions contains only seven. Card numbers and CVVs are masked in this preview. Raw files are unchanged.

## users_data.csv

id | current_age | retirement_age | birth_year | birth_month | gender | address | latitude | longitude | per_capita_income | yearly_income | total_debt | credit_score | num_credit_cards
--- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | ---
825 | 53 | 66 | 1966 | 11 | Female | 462 Rose Lane | 34.15 | -117.76 | $29278 | $59696 | $127613 | 787 | 5
1746 | 53 | 68 | 1966 | 12 | Female | 3606 Federal Boulevard | 40.76 | -73.74 | $37891 | $77254 | $191349 | 701 | 5
1718 | 81 | 67 | 1938 | 11 | Female | 766 Third Drive | 34.02 | -117.89 | $22681 | $33483 | $196 | 698 | 5
708 | 63 | 63 | 1957 | 1 | Female | 3 Madison Street | 40.71 | -73.99 | $163145 | $249925 | $202328 | 722 | 4
1164 | 43 | 70 | 1976 | 9 | Male | 9620 Valley Stream Drive | 37.76 | -122.44 | $53797 | $109687 | $183855 | 675 | 1
68 | 42 | 70 | 1977 | 10 | Male | 58 Birch Lane | 41.55 | -90.6 | $20599 | $41997 | $0 | 704 | 3
1075 | 36 | 67 | 1983 | 12 | Female | 5695 Fifth Street | 38.22 | -85.74 | $25258 | $51500 | $102286 | 672 | 3
1711 | 26 | 67 | 1993 | 12 | Male | 1941 Ninth Street | 45.51 | -122.64 | $26790 | $54623 | $114711 | 728 | 1
1116 | 81 | 66 | 1938 | 7 | Female | 11 Spruce Avenue | 40.32 | -75.32 | $26273 | $42509 | $2895 | 755 | 5
1752 | 34 | 60 | 1986 | 1 | Female | 887 Grant Street | 29.97 | -92.12 | $18730 | $38190 | $81262 | 810 | 1

## cards_data.csv

id | client_id | card_brand | card_type | card_number | expires | cvv | has_chip | num_cards_issued | credit_limit | acct_open_date | year_pin_last_changed | card_on_dark_web
--- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | ---
4524 | 825 | Visa | Debit | •••• 0444 | 12/2022 | ••• | YES | 2 | $24295 | 09/2002 | 2008 | No
2731 | 825 | Visa | Debit | •••• 9986 | 12/2020 | ••• | YES | 2 | $21968 | 04/2014 | 2014 | No
3701 | 825 | Visa | Debit | •••• 5491 | 02/2024 | ••• | YES | 2 | $46414 | 07/2003 | 2004 | No
42 | 825 | Visa | Credit | •••• 9057 | 08/2024 | ••• | NO | 1 | $12400 | 01/2003 | 2012 | No
4659 | 825 | Mastercard | Debit (Prepaid) | •••• 6011 | 03/2009 | ••• | YES | 1 | $28 | 09/2008 | 2009 | No
4537 | 1746 | Visa | Credit | •••• 2993 | 09/2003 | ••• | YES | 1 | $27500 | 09/2003 | 2012 | No
1278 | 1746 | Visa | Debit | •••• 8631 | 07/2022 | ••• | YES | 2 | $28508 | 02/2011 | 2011 | No
3687 | 1746 | Mastercard | Debit | •••• 0948 | 06/2022 | ••• | YES | 2 | $9022 | 07/2003 | 2015 | No
3465 | 1746 | Mastercard | Debit (Prepaid) | •••• 9326 | 11/2020 | ••• | YES | 2 | $54 | 06/2010 | 2015 | No
3754 | 1746 | Mastercard | Debit (Prepaid) | •••• 8701 | 02/2023 | ••• | YES | 1 | $99 | 07/2006 | 2012 | No

## transactions_data.csv

id | date | client_id | card_id | amount | use_chip | merchant_id | merchant_city | merchant_state | zip | mcc | errors
--- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | ---
7475327 | 2010-01-01 00:01:00 | 1556 | 2972 | $-77.00 | Swipe Transaction | 59935 | Beulah | ND | 58523.0 | 5499 | ∅
7475328 | 2010-01-01 00:02:00 | 561 | 4575 | $14.57 | Swipe Transaction | 67570 | Bettendorf | IA | 52722.0 | 5311 | ∅
7475329 | 2010-01-01 00:02:00 | 1129 | 102 | $80.00 | Swipe Transaction | 27092 | Vista | CA | 92084.0 | 4829 | ∅
7475331 | 2010-01-01 00:05:00 | 430 | 2860 | $200.00 | Swipe Transaction | 27092 | Crown Point | IN | 46307.0 | 4829 | ∅
7475332 | 2010-01-01 00:06:00 | 848 | 3915 | $46.41 | Swipe Transaction | 13051 | Harwood | MD | 20776.0 | 5813 | ∅
7475333 | 2010-01-01 00:07:00 | 1807 | 165 | $4.81 | Swipe Transaction | 20519 | Bronx | NY | 10464.0 | 5942 | ∅
7475334 | 2010-01-01 00:09:00 | 1556 | 2972 | $77.00 | Swipe Transaction | 59935 | Beulah | ND | 58523.0 | 5499 | ∅
7475335 | 2010-01-01 00:14:00 | 1684 | 2140 | $26.46 | Online Transaction | 39021 | ONLINE | ∅ | ∅ | 4784 | ∅
7475336 | 2010-01-01 00:21:00 | 335 | 5131 | $261.58 | Online Transaction | 50292 | ONLINE | ∅ | ∅ | 7801 | ∅
7475337 | 2010-01-01 00:21:00 | 351 | 1112 | $10.74 | Swipe Transaction | 3864 | Flushing | NY | 11355.0 | 5813 | ∅

## marketing_touchpoints.csv

touch_id | anonymous_id | client_id | touch_ts | channel | utm_source | utm_medium | utm_campaign | device | landing_page
--- | --- | --- | --- | --- | --- | --- | --- | --- | ---
t_000000001 | anon_000000001 | 1718 | 2019-03-10 19:40:20 | paid_search_brand | google | cpc | brand_exact | desktop | /compare
t_000000002 | anon_000000001 | 1718 | 2019-03-10 23:00:02 | paid_search_brand | google | cpc | brand_phrase | mobile | /cards/rewards
t_000000003 | anon_000000001 | 1718 | 2019-03-12 11:56:38 | paid_search_brand | google | cpc | brand_exact | desktop | /apply
t_000000004 | anon_000000001 | 1718 | 2019-03-12 13:25:25 | organic_search | google | organic | organic | desktop | /cards
t_000000005 | anon_000000001 | 1718 | 2019-03-15 05:36:16 | paid_search_brand | google | cpc | brand_exact | mobile | /cards/rewards
t_000000006 | anon_000000001 | 1718 | 2019-03-16 22:15:16 | paid_search_brand | google | cpc | brand_exact | mobile | /cards/rewards
t_000000007 | anon_000000001 | 1718 | 2019-06-06 00:50:44 | email_lifecycle | braze | email | onboarding_drip | tablet | /compare
t_000000008 | anon_000000001 | 1718 | 2019-06-18 00:53:35 | email_lifecycle | braze | email | cross_sell_card | tablet | /
t_000000009 | anon_000000002 | 1711 | 2019-12-14 00:18:13 | paid_search_nonbrand | google | cpc | generic_cards | mobile | /blog/credit-basics
t_000000010 | anon_000000002 | 1711 | 2019-12-21 01:42:39 | organic_search | google | organic | organic | mobile | /cards

## channel_spend.csv

spend_date | channel | campaign | spend | impressions | clicks | platform_reported_conversions
--- | --- | --- | --- | --- | --- | ---
2016-01-01 | paid_search_brand | brand_exact | 210.14 | 15010 | 852 | 0.00
2016-01-01 | paid_search_brand | brand_phrase | 210.14 | 15010 | 852 | 0.00
2016-01-01 | paid_search_nonbrand | generic_cards | 249.95 | 22722 | 792 | 0.00
2016-01-01 | paid_search_nonbrand | compare_cards | 249.95 | 22722 | 792 | 0.00
2016-01-01 | paid_search_nonbrand | rewards_terms | 249.95 | 22722 | 792 | 0.00
2016-01-01 | paid_social_meta | prospecting_lal | 320.14 | 37664 | 529 | 0.00
2016-01-01 | paid_social_meta | retargeting_site | 320.14 | 37664 | 529 | 0.00
2016-01-01 | paid_social_meta | spring_launch | 320.14 | 37664 | 529 | 0.00
2016-01-01 | paid_social_reddit | r_personalfinance | 97.44 | 17716 | 170 | 0.00
2016-01-01 | paid_social_reddit | r_churning | 97.44 | 17716 | 170 | 0.00

## account_signups.csv

signup_id | client_id | card_id | signup_ts | self_reported_source | signup_landing_page
--- | --- | --- | --- | --- | ---
s_000001 | 1718 | 2379 | 2019-03-21 17:44:00 | social_media | /cards
s_000002 | 1711 | 744 | 2020-01-06 10:32:00 | search | /apply
s_000003 | 1116 | 4905 | 2017-09-05 17:10:00 | social_media | /
s_000004 | 192 | 1766 | 2020-02-25 18:19:00 | other | /
s_000005 | 192 | 1767 | 2020-02-11 13:06:00 | search | /cards
s_000006 | 640 | 745 | 2020-01-08 20:04:00 | social_media | /cards
s_000007 | 1679 | 1459 | 2020-02-10 18:44:00 | search | /blog/credit-basics
s_000008 | 1094 | 1768 | 2020-02-12 17:17:00 | search | /cards
s_000009 | 1660 | 4455 | 2016-08-16 13:51:00 | app_store | /cards
s_000010 | 1747 | 4895 | 2016-09-25 15:49:00 | blog_or_review_site | /compare

## revenue_assumptions.csv

assumption_key | assumption_value | unit | notes
--- | --- | --- | ---
interchange_credit_bps | 180 | bps of settled purchase volume | Blended across MCCs
interchange_debit_bps | 5 | bps of settled purchase volume | Regulated (Durbin) rate
interchange_debit_fixed_cents | 21 | cents per settled transaction | Applies per debit transaction
revolving_apr_pct | 19.99 | annual percentage rate | Applies to revolving credit balances
share_of_credit_balance_revolving_pct | 35 | percent | Finance planning assumption
annual_fee_amex_usd | 95 | usd per card per year | Amex-branded credit cards only
annual_fee_other_usd | 0 | usd per card per year | All other brands

## mcc_codes.json

mcc | description
--- | ---
5812 | Eating Places and Restaurants
5541 | Service Stations
7996 | Amusement Parks, Carnivals, Circuses
5411 | Grocery Stores, Supermarkets
4784 | Tolls and Bridge Fees
4900 | Utilities - Electric, Gas, Water, Sanitary
5942 | Book Stores
5814 | Fast Food Restaurants
4829 | Money Transfer
5311 | Department Stores

## train_fraud_labels.json

transaction_id | fraud_label
--- | ---
10649266 | No
23410063 | No
9316588 | No
12478022 | No
9558530 | No
12532830 | No
19526714 | No
9906964 | No
13224888 | No
13749094 | No
