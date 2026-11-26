# heart_conversation_control.py

class HeartConversationControl:
    """
    Simple controller to detect 'heart' keyword for stopping conversation.
    """

    def __init__(self, keyword="heart"):
        self.keyword = keyword.lower()
        # Words that indicate "heart" is part of a topic, not a command
        self.ignore_if_contains = ['disease', 'rate', 'beat', 'attack', 'health', 'surgery']

    def check_input(self, user_text: str) -> dict:
        """
        Checks if the user wants to stop.
        Returns a dictionary with action instructions.
        """
        text_lower = user_text.lower().strip()
        words = text_lower.split()

        # 1. If user says ONLY "heart"
        if len(words) == 1 and words[0] == self.keyword:
            return {
                'action': 'STOP_IMMEDIATELY',
                'message': '⏸️ Paused.'
            }

        # 2. If user says "query heart" (e.g., "tell me about python heart")
        if len(words) > 1 and words[-1] == self.keyword:
            # Check if it's a medical/technical term like "heart rate"
            is_medical = any(word in words[:-1] for word in self.ignore_if_contains)

            if not is_medical:
                # Remove the last word ("heart") to get the actual query
                clean_query = ' '.join(words[:-1])
                return {
                    'action': 'PROCESS_THEN_STOP',
                    'query': clean_query,
                    'message': 'Processing request then pausing...'
                }

        # 3. Normal conversation
        return {
            'action': 'CONTINUE',
            'query': user_text
        }