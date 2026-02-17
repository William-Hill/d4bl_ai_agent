#!/usr/bin/env python3
"""Insert sample Mississippi NIL content into the vector store for e2e validation."""
import asyncio
import sys
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from d4bl.infra.database import get_database_url, init_db, get_db
from d4bl.infra.vector_store import get_vector_store

# Real and research-based content about Mississippi NIL policies
TEST_ITEMS = [
    {
        "url": "https://www.mississippifreepress.org/mississippi-high-school-athletes-could-earn-nil-money-under-house-bill/",
        "content": (
            "Mississippi House Bill 1400, the 'Mississippi High School Student-Athlete NIL "
            "Protection Act,' was introduced by Rep. Jeffery Harness (D-Fayette) on January 16, "
            "2026. The bill would allow high school athletes to earn up to $10,000 annually from "
            "name, image, and likeness deals. Amounts exceeding $10,000 would go into restricted "
            "trust accounts payable at age 18. The bill prohibits performance-based payments and "
            "payments designed to induce school transfers, while maintaining existing MHSAA "
            "transfer and amateurism rules. Rep. Harness stated the measure would help athletes "
            "at smaller schools: 'They can get paid even if they went to a small school, a 1A "
            "school or a 2A school.' Mississippi is one of only four states — along with Alabama, "
            "Hawaii, and Indiana — that prohibit high school NIL deals, while more than 40 states "
            "allow some form of NIL compensation for high schoolers."
        ),
        "content_type": "html",
        "metadata": {
            "title": "Mississippi High School Athletes Could Earn NIL Money Under House Bill",
            "description": "Details of HB 1400 allowing high school NIL deals in Mississippi",
        },
    },
    {
        "url": "https://magnoliatribune.com/2026/02/10/high-school-nil-legislation-quietly-dies-in-mississippi/",
        "content": (
            "High school NIL legislation quietly died in Mississippi in February 2026. House Bill "
            "1400 did not make it out of committee in the House of Representatives before the "
            "February 12 deadline. Officials with the Mississippi High School Activities "
            "Association (MHSAA), coaches, school administrators and fans spoke out in opposition. "
            "MHSAA Executive Director Rickey Neaves expressed concerns about competitive imbalance, "
            "citing Nebraska's experience where one private school recruited 24 Division-I athletes "
            "and dominated competition after NIL was allowed. Under current MHSAA rules, students "
            "cannot be denied benefit from their own identity, but a high school student-athlete "
            "may sign a NIL deal only under the condition that the student or parents cannot "
            "receive any money or benefits until the student has graduated or used all eligibility."
        ),
        "content_type": "html",
        "metadata": {
            "title": "High School NIL Legislation Quietly Dies in Mississippi",
            "description": "Mississippi HB 1400 fails to advance past committee deadline",
        },
    },
    {
        "url": "https://www.wlbt.com/2026/02/05/game-over-how-nil-could-reshape-mississippi-high-school-sports/",
        "content": (
            "NIL could reshape Mississippi high school sports by exacerbating rural-urban economic "
            "disparities. Coach Higdon in Raleigh, a rural area, noted: 'We got Ward's here in "
            "town you can promote for, but they're not going to be able to pay you $10,000 or "
            "$5,000' — highlighting that rural communities lack the corporate sponsorship "
            "opportunities available in wealthier districts. Coach Tadlock warned that communities "
            "would lose athletes to better-funded areas, stating talent would depart when 'things "
            "get a little tough.' Officials fear NIL will create 'mega teams' as athletes "
            "concentrate in areas with more business opportunities. These economic disparities "
            "disproportionately affect predominantly Black rural communities in the Mississippi "
            "Delta and other underserved regions where schools already face significant funding "
            "challenges."
        ),
        "content_type": "html",
        "metadata": {
            "title": "Game Over: How NIL Could Reshape Mississippi High School Sports",
            "description": "Analysis of rural-urban disparities in high school NIL opportunities",
        },
    },
    {
        "url": "https://www.wlbt.com/2025/12/19/cost-nil/",
        "content": (
            "The cost of NIL in Mississippi reveals significant financial dynamics affecting high "
            "school athletes. Hattiesburg wide receiver Tristen Keys, a Tennessee commit, has an "
            "NIL valuation exceeding $500,000 but cannot receive payment under current Mississippi "
            "rules until exhausting high school eligibility. Fazion Brandon, a North Carolina "
            "recruit from Mississippi, allegedly earns $1.2 million in NIL deals. Some Mississippi "
            "athletes have been approached with offers totaling $1.2 to $1.4 million. Mississippi "
            "consistently produces elite four and five-star recruits, with 12 ranked in ESPN's "
            "top 300. MHSAA Executive Director Rickey Neaves argues high schoolers are 'much too "
            "young' to responsibly manage such sums. The transfer portal has reduced SEC programs' "
            "high school signees by nearly 11% between 2019-2021, further compressing opportunities "
            "for prep athletes statewide."
        ),
        "content_type": "html",
        "metadata": {
            "title": "The Cost of NIL in Mississippi",
            "description": "Financial analysis of NIL deals for Mississippi high school athletes",
        },
    },
    {
        "url": "https://www.ncaa.org/nil-mississippi-college-policy",
        "content": (
            "Mississippi enacted its college-level NIL legislation in 2021, allowing university "
            "athletes to profit from their personal brand. The law permits athletes at Mississippi "
            "State, Ole Miss, and other state universities to sign endorsement deals, appear in "
            "advertisements, and monetize their social media presence. Black athletes make up a "
            "significant portion of revenue-generating sports like football and basketball at SEC "
            "schools. Research has documented disparities in NIL deal values across racial lines, "
            "with white athletes receiving higher average compensation. HBCUs in Mississippi — "
            "Jackson State, Alcorn State, and Mississippi Valley State — face structural "
            "disadvantages in the NIL landscape due to smaller athletic budgets, fewer corporate "
            "partnerships, and less extensive alumni donor networks compared to PWIs."
        ),
        "content_type": "html",
        "metadata": {
            "title": "Mississippi College NIL Policy and Racial Disparities",
            "description": "Overview of college NIL in Mississippi and equity concerns",
        },
    },
    {
        "url": "https://d4bl.org/nil-data-analysis",
        "content": (
            "Data for Black Lives analysis of NIL policy impacts in Mississippi reveals structural "
            "inequities at both the high school and college levels. At the college level, Black "
            "athletes at SEC schools generate a disproportionate share of athletic revenue but "
            "receive lower average NIL compensation. At the high school level, Mississippi's "
            "prohibition on NIL deals uniquely harms Black student-athletes in rural and "
            "underserved communities who could benefit most from early financial opportunities. "
            "The failed House Bill 1400 would have allowed up to $10,000 in annual NIL earnings, "
            "but rural communities — many with majority-Black populations — would likely see "
            "smaller deals than urban counterparts due to fewer local businesses and sponsors. "
            "Policy recommendations include: equity-focused NIL legislation with anti-discrimination "
            "provisions, state-funded NIL collectives for underserved schools, transparency "
            "requirements in deal reporting, partnerships between HBCUs and PWIs to share NIL "
            "resources, and financial literacy programs for young athletes."
        ),
        "content_type": "html",
        "metadata": {
            "title": "D4BL Analysis: NIL Policy Impacts on Black Athletes in Mississippi",
            "description": "Data-driven analysis of NIL disparities and policy recommendations",
        },
    },
]


async def main():
    init_db()
    vector_store = get_vector_store()

    # Use the completed job ID
    job_id = UUID("1adfa2ec-ada7-42db-9859-59314dadac0c")

    async for db in get_db():
        try:
            stored = await vector_store.store_batch(
                db=db, job_id=job_id, items=TEST_ITEMS
            )
            print(f"Stored {stored}/{len(TEST_ITEMS)} items in vector store")
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
        break


if __name__ == "__main__":
    asyncio.run(main())
