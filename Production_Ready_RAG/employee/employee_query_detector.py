import re


class EmployeeQueryDetector:
    """
    Decides whether a question is about the LOGGED-IN employee's
    own private record (database) or about general HR policy /
    company information (RAG knowledge base).

    Two things are returned:

    1. is_employee_query -> bool
    2. query_types       -> list of topics to fetch from the DB
                            ("profile", "leave_balance",
                             "leave_history", "salary")
    """

    # ------------------------------------------------------------
    # Phrases that look first-person but are NOT.
    # "tell me about casual leave" is a POLICY question.
    # These are stripped before first-person detection.
    # ------------------------------------------------------------

    FILLER_PATTERNS = [
        r"\btell me about\b",
        r"\btell me\b",
        r"\bexplain to me\b",
        r"\bexplain me\b",
        r"\bshow me\b",
        r"\bgive me\b",
        r"\bsend me\b",
        r"\blet me know\b",
        r"\bhelp me understand\b",
        r"\bcan you help me\b",
        r"\bhelp me\b",
        r"\bfor me to understand\b",
    ]

    # ------------------------------------------------------------
    # Real first-person / possessive markers
    # ------------------------------------------------------------

    FIRST_PERSON_PATTERNS = [
        r"\bmy\b",
        r"\bmine\b",
        r"\bmyself\b",
        r"\bi\b",
        r"\bi'm\b",
        r"\bim\b",
        r"\bi've\b",
        r"\bfor me\b",
        r"\bto me\b",
        r"\bam i\b",
        r"\bdo i\b",
        r"\bdid i\b",
        r"\bhave i\b",
        r"\bcan i\b",
        r"\bwas i\b",
        r"\bwho am i\b",
    ]

    # ------------------------------------------------------------
    # Topic keywords -> which DB section to load
    # Order matters: the first matching topic list wins for
    # ambiguous words, but ALL matching topics are returned.
    # ------------------------------------------------------------

    SALARY_KEYWORDS = [
        r"\bsalary\b",
        r"\bsalaries\b",
        r"\bpay\b",
        r"\bpaid\b",
        r"\bpayslip\b",
        r"\bpay slip\b",
        r"\bpayroll\b",
        r"\bremuneration\b",
        r"\bincrement\b",
        r"\bappraisal\b",
        r"\bbonus\b",
        r"\bwage\b",
        r"\bwages\b",
        r"\bctc\b",
        r"\bincome\b",
        r"\bearning\b",
        r"\bearnings\b",
        r"\bcompensation\b",
        r"\btake home\b",
        r"\bin hand\b",
        r"\bbasic\b",
    ]

    LEAVE_HISTORY_KEYWORDS = [
        r"\btaken\b",
        r"\btook\b",
        r"\bavailed\b",
        r"\bused\b",
        r"\bhistory\b",
        r"\bapplied\b",
        r"\bthis month\b",
        r"\blast month\b",
        r"\bthis week\b",
        r"\blast week\b",
        r"\bso far\b",
        r"\bpast leaves?\b",
        r"\bupcoming\b",
        r"\bpending leave\b",
        r"\bapproved leave\b",
    ]

    LEAVE_BALANCE_KEYWORDS = [
        r"\bleave\b",
        r"\bleaves\b",
        r"\bbalance\b",
        r"\bremaining\b",
        r"\bleft\b",
        r"\bavailable\b",
        r"\bvacation\b",
        r"\bholidays?\b",
        r"\bcasual\b",
        r"\bsick\b",
        r"\bannual\b",
        r"\bpersonal leave\b",
        r"\bcarry forward\b",
        r"\bencash\b",
    ]

    PROFILE_KEYWORDS = [
        r"\bname\b",
        r"\bwho am i\b",
        r"\bemployee id\b",
        r"\bemp id\b",
        r"\bemployee code\b",
        r"\bemployee number\b",
        r"\bdepartment\b",
        r"\bdept\b",
        r"\bteam\b",
        r"\bdesignation\b",
        r"\brole\b",
        r"\bposition\b",
        r"\bjob title\b",
        r"\btitle\b",
        r"\bmanager\b",
        r"\breporting\b",
        r"\breports to\b",
        r"\bsupervisor\b",
        r"\bboss\b",
        r"\bjoin\b",
        r"\bjoined\b",
        r"\bjoining\b",
        r"\bdoj\b",
        r"\bdate of joining\b",
        r"\bemail\b",
        r"\bmail id\b",
        r"\bphone\b",
        r"\bmobile\b",
        r"\bcontact\b",
        r"\blocation\b",
        r"\bbranch\b",
        r"\boffice\b",
        r"\bbased\b",
        r"\bemployment type\b",
        r"\bfull.?time\b",
        r"\bpart.?time\b",
        r"\bdate of birth\b",
        r"\bdob\b",
        r"\bbirthday\b",
        r"\bgender\b",
        r"\bstatus\b",
        r"\bprofile\b",
        r"\bmy details\b",
        r"\bmy detail\b",
        r"\bmy info\b",
        r"\bmy information\b",
        r"\babout me\b",
        r"\bwork for\b",
        r"\bworking for\b",
        r"\bwork at\b",
        r"\bworking at\b",
        r"\bwork in\b",
        r"\bworking in\b",
        r"\bexperience\b",
        r"\btenure\b",
        r"\bhow long\b",
    ]

    TOPIC_MAP = [
        ("salary", SALARY_KEYWORDS),
        ("leave_history", LEAVE_HISTORY_KEYWORDS),
        ("leave_balance", LEAVE_BALANCE_KEYWORDS),
        ("profile", PROFILE_KEYWORDS),
    ]

    # ------------------------------------------------------------
    # Strong phrases that are ALWAYS personal, even if the
    # first-person / topic heuristics miss them.
    # ------------------------------------------------------------

    EXPLICIT_PERSONAL_PATTERNS = [
        r"\bmy leave\b",
        r"\bmy leaves\b",
        r"\bmy leave balance\b",
        r"\bleave balance\b",
        r"\bremaining leaves?\b",
        r"\bleaves? remaining\b",
        r"\bmy salary\b",
        r"\bmy pay\b",
        r"\bmy profile\b",
        r"\bmy department\b",
        r"\bmy designation\b",
        r"\bmy manager\b",
        r"\bmy joining date\b",
        r"\bmy name\b",
        r"\bmy employee id\b",
        r"\bwho am i\b",
        r"\bwhen did i join\b",
        r"\bhow many leaves do i\b",
        r"\bhow much leave do i\b",
    ]

    # ============================================================
    # Public API
    # ============================================================

    @classmethod
    def classify(cls, question, extra_question=None):
        """
        question       : the original user question
        extra_question : optionally the rewritten / resolved
                         question (used for follow-ups such as
                         "what about next month?")

        Returns:
            {
                "is_employee_query": bool,
                "query_types": ["leave_balance", ...],
                "reason": "..."
            }
        """

        candidates = [question]

        if extra_question and extra_question != question:
            candidates.append(extra_question)

        best = {
            "is_employee_query": False,
            "query_types": [],
            "reason": "No personal reference detected"
        }

        for candidate in candidates:

            result = cls._classify_single(candidate)

            if result["is_employee_query"]:
                return result

            # keep the most informative negative result
            if result["query_types"]:
                best = result

        return best

    @classmethod
    def _classify_single(cls, question):

        if not question:
            return {
                "is_employee_query": False,
                "query_types": [],
                "reason": "Empty question"
            }

        text = question.lower().strip()

        # ----------------------------------------------------
        # 1. Explicit personal phrases -> short circuit
        # ----------------------------------------------------

        explicit = any(
            re.search(pattern, text)
            for pattern in cls.EXPLICIT_PERSONAL_PATTERNS
        )

        # ----------------------------------------------------
        # 2. Remove "tell me about ..." style filler so that
        #    policy questions are not mistaken for personal
        #    questions because of the word "me".
        # ----------------------------------------------------

        stripped = text

        for pattern in cls.FILLER_PATTERNS:
            stripped = re.sub(pattern, " ", stripped)

        # ----------------------------------------------------
        # 3. First-person detection
        # ----------------------------------------------------

        has_first_person = any(
            re.search(pattern, stripped)
            for pattern in cls.FIRST_PERSON_PATTERNS
        )

        # ----------------------------------------------------
        # 4. Topic detection
        # ----------------------------------------------------

        query_types = []

        for topic, keywords in cls.TOPIC_MAP:

            for keyword in keywords:

                if re.search(keyword, text):
                    query_types.append(topic)
                    break

        # "how many leaves have I taken" -> history, not balance
        if (
            "leave_history" in query_types
            and "leave_balance" in query_types
        ):
            # keep both: the LLM benefits from balance + history
            pass

        # ----------------------------------------------------
        # 5. Decision
        # ----------------------------------------------------

        if explicit:

            if not query_types:
                query_types = ["profile"]

            return {
                "is_employee_query": True,
                "query_types": cls._dedupe(query_types),
                "reason": "Explicit personal phrase matched"
            }

        if has_first_person and query_types:

            return {
                "is_employee_query": True,
                "query_types": cls._dedupe(query_types),
                "reason": (
                    "First-person reference with personal topic: "
                    + ", ".join(cls._dedupe(query_types))
                )
            }

        if has_first_person and not query_types:

            # e.g. "what about me?" -> ambiguous.
            # Load the profile so the LLM has identity context,
            # but let RAG run as well.
            return {
                "is_employee_query": False,
                "query_types": ["profile"],
                "reason": (
                    "First-person reference without a "
                    "recognised personal topic"
                )
            }

        return {
            "is_employee_query": False,
            "query_types": [],
            "reason": "General HR / company question"
        }

    @staticmethod
    def _dedupe(items):

        seen = []

        for item in items:
            if item not in seen:
                seen.append(item)

        return seen

    # ============================================================
    # Backwards-compatible helpers
    # ============================================================

    @classmethod
    def is_employee_query(cls, question):

        return cls.classify(question)["is_employee_query"]

    @classmethod
    def get_query_type(cls, question):

        types = cls.classify(question)["query_types"]

        return types[0] if types else None
