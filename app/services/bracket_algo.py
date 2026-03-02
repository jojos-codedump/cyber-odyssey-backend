import math
import random
import uuid
from typing import List, Dict, Any

def get_next_power_of_2(n: int) -> int:
    """
    Calculates the next highest power of 2 for a given number.
    For example: 3 -> 4, 6 -> 8, 16 -> 16, 21 -> 32.
    """
    if n == 0:
        return 1
    # If n is already a power of 2, this returns n
    return 2 ** math.ceil(math.log2(n))

def generate_perfect_bracket(participants: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Generates a full tournament bracket JSON structure.
    
    Args:
        participants: A list of dictionaries containing participant/team info.
                      Example: [{"id": "uuid1", "name": "Team Alpha"}, ...]
                      
    Returns:
        A dictionary representing the mathematical tournament tree.
    """
    num_participants = len(participants)
    
    # 1. Calculate the perfect bracket size
    bracket_size = get_next_power_of_2(num_participants)
    num_byes = bracket_size - num_participants
    
    # 2. Inject "Byes" into the pool
    pool = participants.copy()
    for i in range(num_byes):
        pool.append({
            "id": f"bye_{uuid.uuid4().hex[:8]}", 
            "name": "BYE", 
            "is_bye": True
        })
        
    # 3. Randomize the pool to ensure fair, unbiased seeding
    random.shuffle(pool)
    
    rounds = []
    
    # 4. Generate Round 1 (The initial matches)
    round_1_matches = []
    for i in range(0, bracket_size, 2):
        p1 = pool[i]
        p2 = pool[i+1]
        
        # Auto-advance logic: If a participant is paired with a BYE, they win automatically.
        winner_id = None
        if p1.get("is_bye"):
            winner_id = p2.get("id")
        elif p2.get("is_bye"):
            winner_id = p1.get("id")
            
        round_1_matches.append({
            "match_id": str(uuid.uuid4()),
            "participant1": p1,
            "participant2": p2,
            "winner_id": winner_id
        })
        
    rounds.append({
        "round_number": 1,
        "matches": round_1_matches
    })
    
    # 5. Pre-generate subsequent empty rounds to form the complete tree
    # This makes the frontend UI rendering significantly easier.
    current_matches_count = len(round_1_matches)
    round_num = 2
    
    while current_matches_count > 1:
        current_matches_count //= 2
        future_matches = []
        for _ in range(current_matches_count):
            future_matches.append({
                "match_id": str(uuid.uuid4()),
                "participant1": None,
                "participant2": None,
                "winner_id": None
            })
            
        rounds.append({
            "round_number": round_num,
            "matches": future_matches
        })
        round_num += 1

    # 6. Return the finalized structured JSON
    return {
        "metadata": {
            "total_actual_participants": num_participants,
            "mathematical_bracket_size": bracket_size,
            "total_rounds": len(rounds)
        },
        "rounds": rounds
    }