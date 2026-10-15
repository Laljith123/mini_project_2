"""
Comprehensive Test Suite for College Admission Enquiry Assistant.

Covers:
1. Security Engineering (anti-XSS, rate limiting, proxy headers, traversal protection, session tokens)
2. Data Pipeline Engineering (validation, referential integrity, schema enforcement, transformations, FAQ matching)
3. AI Engine (intent classification, program entity detection, offline composer, grounding)
4. WSGI Web Application (routing, JSON API, session persistence, health probes, error handling)
"""

import io
import json
import os
import unittest
from urllib.parse import urlencode

import ai_engine
import app
import data_pipeline
import security

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KB_PATH = os.path.join(BASE_DIR, "knowledge_base.json")


class TestSecurity(unittest.TestCase):
    def setUp(self):
        security.reset_rate_limits()

    def test_sanitize_input_xss(self):
        dirty = "<script>alert('xss')</script>Hello <b>World</b>"
        cleaned = security.sanitize_input(dirty)
        self.assertNotIn("<script>", cleaned)
        self.assertNotIn("<b>", cleaned)
        self.assertEqual(cleaned, "Hello World")

    def test_sanitize_input_control_characters(self):
        dirty = "CSE\x00\x08Admission\x1fEnquiry"
        cleaned = security.sanitize_input(dirty)
        self.assertEqual(cleaned, "CSEAdmissionEnquiry")

    def test_escape_html(self):
        escaped = security.escape_html('<a href="test">&amp;</a>')
        self.assertEqual(escaped, "&lt;a href=&quot;test&quot;&gt;&amp;amp;&lt;/a&gt;")

    def test_client_ip_extraction(self):
        # Direct connection
        env1 = {"REMOTE_ADDR": "192.168.1.50"}
        self.assertEqual(security.client_ip(env1), "192.168.1.50")

        # Reverse proxy / AWS ALB X-Forwarded-For chain
        env2 = {"HTTP_X_FORWARDED_FOR": "203.0.113.195, 70.41.3.18, 150.172.238.178", "REMOTE_ADDR": "10.0.0.1"}
        self.assertEqual(security.client_ip(env2), "203.0.113.195")

    def test_rate_limiting(self):
        ip = "198.51.100.1"
        for _ in range(30):
            self.assertTrue(security.check_rate_limit(ip, max_requests=30, window_secs=60))
        # 31st request exceeds limit
        self.assertFalse(security.check_rate_limit(ip, max_requests=30, window_secs=60))

    def test_session_lifecycle(self):
        env_empty = {}
        sid, is_new = security.get_session(env_empty)
        self.assertTrue(is_new)
        self.assertEqual(len(sid), 32)

        # Subsequent request with cookie
        env_with_cookie = {"HTTP_COOKIE": f"other=123; sid={sid}; test=abc"}
        sid2, is_new2 = security.get_session(env_with_cookie)
        self.assertFalse(is_new2)
        self.assertEqual(sid, sid2)

    def test_static_path_traversal_blocked(self):
        def start_response(status, headers):
            self.status = status
            self.headers = headers

        res = security.serve_static("/static/../../app.py", start_response, [])
        self.assertIn("403", self.status)


class TestDataPipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw_kb = data_pipeline.load_raw(KB_PATH)

    def test_valid_knowledge_base(self):
        findings, errors = data_pipeline.validate(self.raw_kb)
        self.assertEqual(errors, 0, f"Validation errors found: {findings}")

    def test_validation_detects_missing_fields(self):
        bad_kb = {"programs": [{"code": "TEST"}], "fee_structure": [], "facilities": [], "faqs": [], "admission_procedure": ["step 1"]}
        findings, errors = data_pipeline.validate(bad_kb)
        self.assertGreater(errors, 0)
        self.assertTrue(any("missing field" in f for f in findings))

    def test_validation_detects_unknown_program_in_fees(self):
        bad_kb = {
            "programs": [{"code": "CSE", "name": "CSE", "duration": "4", "intake": 60, "eligibility": "E", "first_year_fees": 1000}],
            "fee_structure": [{"program": "NONEXISTENT", "component": "Tuition", "amount": 5000, "frequency": "yearly"}],
            "facilities": [],
            "faqs": [],
            "admission_procedure": ["step 1"],
        }
        findings, errors = data_pipeline.validate(bad_kb)
        self.assertGreater(errors, 0)
        self.assertTrue(any("unknown program code" in f for f in findings))

    def test_transform_derived_views(self):
        kb_copy = json.loads(json.dumps(self.raw_kb))
        transformed = data_pipeline.transform(kb_copy)
        self.assertIn("derived_total_first_year_fees", transformed)
        self.assertIn("keyword_index", transformed)

        # Check fee math for CSE: 65000 + 12000 + 8000 = 85000
        self.assertEqual(transformed["derived_total_first_year_fees"]["CSE"], 85000)

    def test_faq_matcher(self):
        transformed = data_pipeline.transform(json.loads(json.dumps(self.raw_kb)))
        match = data_pipeline.get_faq_match(transformed, "Are scholarships available for students?")
        self.assertIsNotNone(match)
        self.assertIn("scholarship", match["q"].lower())


class TestAIEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kb = data_pipeline.load_and_validate(KB_PATH)
        cls.assistant = ai_engine.GPTAssistant(cls.kb)

    def test_program_detection(self):
        self.assertEqual(ai_engine.detect_program("What are the fees for Computer Science?"), "CSE")
        self.assertEqual(ai_engine.detect_program("What is the intake for ece?"), "ECE")
        self.assertEqual(ai_engine.detect_program("Tell me about mechanical engineering"), "MECH")
        self.assertEqual(ai_engine.detect_program("Is IT degree offered?"), "IT")
        self.assertEqual(ai_engine.detect_program("What about artificial intelligence and data science?"), "AI-DS")

    def test_intent_classification(self):
        i1, _, _ = ai_engine.classify_intent("What is the eligibility criteria for CSE?", self.kb)
        self.assertEqual(i1, "eligibility")

        i2, _, _ = ai_engine.classify_intent("How much does the tuition fee cost?", self.kb)
        self.assertEqual(i2, "fees")

        i3, _, _ = ai_engine.classify_intent("What is the admission procedure and application process?", self.kb)
        self.assertEqual(i3, "procedure")

        i4, _, _ = ai_engine.classify_intent("What hostel and sports facilities are available?", self.kb)
        self.assertEqual(i4, "facilities")

        i5, _, _ = ai_engine.classify_intent("Which B.Tech courses are offered?", self.kb)
        self.assertEqual(i5, "courses")

        i6, _, _ = ai_engine.classify_intent("Is there a management quota?", self.kb)
        self.assertEqual(i6, "faq")

    def test_offline_composer_all_intents(self):
        for intent in ("eligibility", "courses", "fees", "procedure", "facilities", "general"):
            retrieved = ai_engine.retrieve(self.kb, intent, "CSE")
            resp = ai_engine.compose_offline("Tell me details", intent, "CSE", self.kb, retrieved)
            self.assertTrue(len(resp) > 20, f"Response too short for {intent}")

    def test_assistant_full_answer_flow(self):
        answer, meta = self.assistant.answer("How much is the fee for B.Tech ECE?")
        self.assertIn("text", answer)
        self.assertIn("html", answer)
        self.assertEqual(meta["intent"], "fees")
        self.assertEqual(meta["program"], "ECE")
        self.assertIn("85,000", answer["text"])


class TestWSGIApplication(unittest.TestCase):
    def setUp(self):
        security.reset_rate_limits()

    def _call_app(self, method="GET", path="/", query="", body=None, headers=None):
        environ = {
            "REQUEST_METHOD": method,
            "PATH_INFO": path,
            "QUERY_STRING": query,
            "wsgi.input": io.BytesIO(body or b""),
            "CONTENT_LENGTH": str(len(body or b"")),
            "REMOTE_ADDR": "127.0.0.1",
        }
        if headers:
            for k, v in headers.items():
                header_key = "HTTP_" + k.upper().replace("-", "_")
                environ[header_key] = v
                if k.lower() == "content-type":
                    environ["CONTENT_TYPE"] = v

        captured = {}

        def start_response(status, response_headers):
            captured["status"] = status
            captured["headers"] = response_headers

        result_iter = app.application(environ, start_response)
        captured["body"] = b"".join(result_iter).decode("utf-8", "replace")
        return captured

    def test_health_probe(self):
        res = self._call_app("GET", "/health")
        self.assertIn("200 OK", res["status"])
        data = json.loads(res["body"])
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["service"], "admission-assistant")

    def test_get_home_page(self):
        res = self._call_app("GET", "/")
        self.assertIn("200 OK", res["status"])
        self.assertIn("Sri Manakula Vinayagar Engineering College", res["body"])
        # Check Set-Cookie header on first request
        cookie_header = [v for k, v in res["headers"] if k.lower() == "set-cookie"]
        self.assertTrue(len(cookie_header) > 0)
        self.assertIn("sid=", cookie_header[0])

    def test_get_kb_browser(self):
        res = self._call_app("GET", "/kb")
        self.assertIn("200 OK", res["status"])
        self.assertIn("Validated Knowledge Base", res["body"])
        self.assertIn("CSE", res["body"])

    def test_post_ask_form(self):
        form_data = urlencode({"question": "What is the eligibility for CSE?"}).encode("utf-8")
        res = self._call_app("POST", "/ask", body=form_data, headers={"content-type": "application/x-www-form-urlencoded"})
        self.assertIn("200 OK", res["status"])
        self.assertIn("Eligibility for B.Tech Computer Science", res["body"])

    def test_post_api_chat_json(self):
        req_data = json.dumps({"question": "What facilities do you have?"}).encode("utf-8")
        res = self._call_app("POST", "/api/chat", body=req_data, headers={"content-type": "application/json", "accept": "application/json"})
        self.assertIn("200 OK", res["status"])
        data = json.loads(res["body"])
        self.assertIn("question", data)
        self.assertIn("answer", data)
        self.assertIn("meta", data)
        self.assertEqual(data["meta"]["intent"], "facilities")

    def test_clear_session(self):
        res = self._call_app("GET", "/clear")
        self.assertIn("303 See Other", res["status"])
        loc = [v for k, v in res["headers"] if k.lower() == "location"]
        self.assertEqual(loc, ["/"])

    def test_empty_question_handling(self):
        form_data = urlencode({"question": "   "}).encode("utf-8")
        res = self._call_app("POST", "/ask", body=form_data, headers={"content-type": "application/x-www-form-urlencoded"})
        self.assertIn("400 Bad Request", res["status"])
        self.assertIn("Please type a question before submitting", res["body"])

    def test_oversized_question(self):
        form_data = urlencode({"question": "A" * 501}).encode("utf-8")
        res = self._call_app("POST", "/ask", body=form_data, headers={"content-type": "application/x-www-form-urlencoded"})
        self.assertIn("400 Bad Request", res["status"])
        self.assertIn("keep your question under 500 characters", res["body"])

    def test_malformed_json_api(self):
        res = self._call_app("POST", "/api/chat", body=b"{bad json", headers={"content-type": "application/json", "accept": "application/json"})
        self.assertIn("400 Bad Request", res["status"])
        data = json.loads(res["body"])
        self.assertIn("error", data)

    def test_session_isolation(self):
        # Session A asks question
        sid_a = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        form_a = urlencode({"question": "What is the fee for ECE?"}).encode("utf-8")
        self._call_app("POST", "/ask", body=form_a, headers={"cookie": f"sid={sid_a}", "content-type": "application/x-www-form-urlencoded"})

        # Session B views chat - should NOT see Session A's question
        sid_b = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
        res_b = self._call_app("GET", "/", headers={"cookie": f"sid={sid_b}"})
        self.assertNotIn("What is the fee for ECE?", res_b["body"])

        # Session A views chat - SHOULD see their question
        res_a = self._call_app("GET", "/", headers={"cookie": f"sid={sid_a}"})
        self.assertIn("What is the fee for ECE?", res_a["body"])

    def test_rate_limit_wsgi_enforcement(self):
        headers = {"remote_addr": "203.0.113.88"}
        # Send 30 requests within limit
        for _ in range(30):
            res = self._call_app("GET", "/health", headers=headers)
            self.assertIn("200 OK", res["status"])

        # 31st request from same IP should get 429
        res_blocked = self._call_app("GET", "/health", headers=headers)
        self.assertIn("429 Too Many Requests", res_blocked["status"])


if __name__ == "__main__":
    unittest.main()

