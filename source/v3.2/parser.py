from lexer import *
import ast


class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0

    def peek(self):
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return None

    def consume(self):
        token = self.peek()
        if token is not None:
            self.pos += 1
        return token

    def parse(self):
        nodes = []
        while self.peek() is not None:
            nodes.append(self.parse_statement())
        if len(nodes) == 1:
            return nodes[0]
        return ("BLOCK", nodes)

    def parse_statement(self):
        token = self.peek()
        if token is None:
            raise SyntaxError("Unexpected end of input")

        # stray else should be reported clearly
        if token[0] == "ELSE":
            raise SyntaxError("Unexpected else without matching if")

        # import / from-import
        if token[0] == "IMPORT":
            self.consume()
            name = self.consume()
            if not name or name[0] != "IDENTIFIER":
                raise SyntaxError("Expected module name after import")
            alias = None
            if self.peek() and self.peek()[0] == "AS":
                self.consume()
                a = self.consume()
                if not a or a[0] != "IDENTIFIER":
                    raise SyntaxError("Expected alias after as")
                alias = a[1]
            return ("IMPORT", name[1], alias)
        if token[0] == "RAISE":
            self.consume()
            expr = self.parse_expression()
            return ("RAISE", expr)
        if token[0] == "FROM":
            self.consume()
            mod = self.consume()
            if not mod or mod[0] != "IDENTIFIER":
                raise SyntaxError("Expected module name after from")
            if not self.peek() or self.peek()[0] != "IMPORT":
                raise SyntaxError("Expected import after from")
            self.consume()
            nm = self.consume()
            if not nm or nm[0] != "IDENTIFIER":
                raise SyntaxError("Expected name after from X import")
            alias = None
            if self.peek() and self.peek()[0] == "AS":
                self.consume()
                a = self.consume()
                if not a or a[0] != "IDENTIFIER":
                    raise SyntaxError("Expected alias after as")
                alias = a[1]
            return ("FROMIMPORT", mod[1], nm[1], alias)

        # try/except/finally
        if token[0] == "TRY":
            self.consume()
            if not self.peek() or self.peek()[0] != "LBRACE":
                raise SyntaxError("Expected { after try")
            self.consume()
            try_body = []
            while self.peek() and self.peek()[0] != "RBRACE":
                try_body.append(self.parse_statement())
            if not self.peek() or self.peek()[0] != "RBRACE":
                raise SyntaxError("Expected } after try body")
            self.consume()
            excepts = []
            finally_block = None
            while self.peek() and self.peek()[0] == "EXCEPT":
                self.consume()
                ex_name = None
                if self.peek() and self.peek()[0] == "IDENTIFIER":
                    ex_name = self.consume()[1]
                if not self.peek() or self.peek()[0] != "LBRACE":
                    raise SyntaxError("Expected { after except")
                self.consume()
                ex_body = []
                while self.peek() and self.peek()[0] != "RBRACE":
                    ex_body.append(self.parse_statement())
                if not self.peek() or self.peek()[0] != "RBRACE":
                    raise SyntaxError("Expected } after except body")
                self.consume()
                excepts.append((ex_name, ("BLOCK", ex_body)))
            if self.peek() and self.peek()[0] == "FINALLY":
                self.consume()
                if not self.peek() or self.peek()[0] != "LBRACE":
                    raise SyntaxError("Expected { after finally")
                self.consume()
                fin_body = []
                while self.peek() and self.peek()[0] != "RBRACE":
                    fin_body.append(self.parse_statement())
                if not self.peek() or self.peek()[0] != "RBRACE":
                    raise SyntaxError("Expected } after finally body")
                self.consume()
                finally_block = ("BLOCK", fin_body)
            return ("TRY", ("BLOCK", try_body), excepts, finally_block)

        # class def
        if token[0] == "CLASS":
            self.consume()
            name = self.consume()
            if not name or name[0] != "IDENTIFIER":
                raise SyntaxError("Expected class name after class")
            if not self.peek() or self.peek()[0] != "LBRACE":
                raise SyntaxError("Expected { for class body")
            self.consume()
            body = []
            while self.peek() and self.peek()[0] != "RBRACE":
                body.append(self.parse_statement())
            if not self.peek() or self.peek()[0] != "RBRACE":
                raise SyntaxError("Expected } after class body")
            self.consume()
            return ("CLASS", name[1], ("BLOCK", body))

        # if statement
        if token[0] == "IF":
            self.consume()
            cond = self.parse_expression()
            if not self.peek() or self.peek()[0] != "LBRACE":
                raise SyntaxError("Expected { after if condition")
            self.consume()
            body = []
            while self.peek() and self.peek()[0] != "RBRACE":
                body.append(self.parse_statement())
            if not self.peek() or self.peek()[0] != "RBRACE":
                raise SyntaxError("Expected } after if body")
            self.consume()
            # optional else / else if
            else_block = None
            if self.peek() and self.peek()[0] == "ELSE":
                self.consume()
                # else-if: allow `else if` to be parsed as nested IF
                if self.peek() and self.peek()[0] == "IF":
                    else_block = self.parse_statement()
                else:
                    if not self.peek() or self.peek()[0] != "LBRACE":
                        raise SyntaxError("Expected { after else")
                    self.consume()
                    else_body = []
                    while self.peek() and self.peek()[0] != "RBRACE":
                        else_body.append(self.parse_statement())
                    if not self.peek() or self.peek()[0] != "RBRACE":
                        raise SyntaxError("Expected } after else body")
                    self.consume()
                    else_block = ("BLOCK", else_body)
            return ("IF", cond, ("BLOCK", body), else_block)

        # while loop
        if token[0] == "WHILE":
            self.consume()
            cond = self.parse_expression()
            if not self.peek() or self.peek()[0] != "LBRACE":
                raise SyntaxError("Expected { after while condition")
            self.consume()
            body = []
            while self.peek() and self.peek()[0] != "RBRACE":
                body.append(self.parse_statement())
            if not self.peek() or self.peek()[0] != "RBRACE":
                raise SyntaxError("Expected } after while body")
            self.consume()
            return ("WHILE", cond, ("BLOCK", body))

        # for loop
        if token[0] == "FOR":
            self.consume()
            var = self.consume()
            if not var or var[0] != "IDENTIFIER":
                raise SyntaxError("Expected identifier after for")
            if not self.peek() or self.peek()[0] != "IN":
                raise SyntaxError("Expected in in for")
            self.consume()
            iterable = self.parse_expression()
            if not self.peek() or self.peek()[0] != "LBRACE":
                raise SyntaxError("Expected { after for")
            self.consume()
            body = []
            while self.peek() and self.peek()[0] != "RBRACE":
                body.append(self.parse_statement())
            if not self.peek() or self.peek()[0] != "RBRACE":
                raise SyntaxError("Expected } after for body")
            self.consume()
            return ("FOR", var[1], iterable, ("BLOCK", body))

        # function def
        if token[0] == "FUNCTION":
            self.consume()
            name = self.consume()
            if not name or name[0] != "IDENTIFIER":
                raise SyntaxError("Expected function name")
            if not self.peek() or self.peek()[0] != "LPAREN":
                raise SyntaxError("Expected ( after function name")
            self.consume()
            params = []
            if self.peek() and self.peek()[0] != "RPAREN":
                while True:
                    p = self.consume()
                    if not p or p[0] != "IDENTIFIER":
                        raise SyntaxError("Expected parameter name")
                    params.append(p[1])
                    if self.peek() and self.peek()[0] == "COMMA":
                        self.consume()
                        continue
                    break
            if not self.peek() or self.peek()[0] != "RPAREN":
                raise SyntaxError("Expected ) after params")
            self.consume()
            if not self.peek() or self.peek()[0] != "LBRACE":
                raise SyntaxError("Expected { for function body")
            self.consume()
            body = []
            while self.peek() and self.peek()[0] != "RBRACE":
                body.append(self.parse_statement())
            if not self.peek() or self.peek()[0] != "RBRACE":
                raise SyntaxError("Expected } after function body")
            self.consume()
            return ("FUNCDEF", name[1], params, ("BLOCK", body))

        # return
        if token[0] == "RETURN":
            self.consume()
            expr = self.parse_expression()
            return ("RETURN", expr)

        # assignment (support attribute/index lhs)
        if token[0] == "IDENTIFIER":
            save = self.pos
            name = self.consume()[1]
            lhs = ("VAR", name)
            try:
                # collect postfixes (dot/index)
                while True:
                    t = self.peek()
                    if not t:
                        break
                    if t[0] == "DOT":
                        self.consume()
                        nm = self.consume()
                        if not nm or nm[0] != "IDENTIFIER":
                            raise SyntaxError("Expected attribute name after .")
                        lhs = ("ATTR", lhs, nm[1])
                        continue
                    if t[0] == "LBRACKET":
                        self.consume()
                        idx = self.parse_expression()
                        if not self.peek() or self.peek()[0] != "RBRACKET":
                            raise SyntaxError("Expected ] after index")
                        self.consume()
                        lhs = ("INDEX", lhs, idx)
                        continue
                    break
                # augmented assignment support
                if self.peek() and self.peek()[0] in (
                    "PLUSEQ",
                    "MINUSEQ",
                    "TIMESEQ",
                    "DIVEQ",
                    "MODEQ",
                ):
                    op = self.consume()[0]
                    op_map = {
                        "PLUSEQ": "+=",
                        "MINUSEQ": "-=",
                        "TIMESEQ": "*=",
                        "DIVEQ": "/=",
                        "MODEQ": "%=",
                    }
                    expr = self.parse_expression()
                    return ("AUGASSIGN", op_map[op], lhs, expr)

                if self.peek() and self.peek()[0] == "ASSIGN":
                    self.consume()
                    expr = self.parse_expression()
                    return ("ASSIGN_LHS", lhs, expr)
            except Exception:
                # restore on error
                self.pos = save
                raise
            # not an assignment, restore position
            self.pos = save

        # otherwise expression
        return self.parse_expression()

    def parse_expression(self):
        return self.parse_or()

    def parse_or(self):
        node = self.parse_and()
        while True:
            t = self.peek()
            if t and t[0] == "OR":
                self.consume()
                right = self.parse_and()
                node = ("OR", node, right)
                continue
            break
        return node

    def parse_and(self):
        node = self.parse_not()
        while True:
            t = self.peek()
            if t and t[0] == "AND":
                self.consume()
                right = self.parse_not()
                node = ("AND", node, right)
                continue
            break
        return node

    def parse_not(self):
        t = self.peek()
        if t and t[0] == "NOT":
            self.consume()
            return ("NOT", self.parse_not())
        return self.parse_compare()

    def parse_compare(self):
        node = self.parse_add()
        t = self.peek()
        if t and t[0] in (
            "EQUALS",
            "NOT_EQUALS",
            "LESS_THAN",
            "GREATER_THAN",
            "LESS_EQUAL",
            "GREATER_EQUAL",
        ):
            op = self.consume()[1]
            right = self.parse_compare()
            return ("COMPARE", op, node, right)
        return node

    def parse_add(self):
        node = self.parse_term()
        while True:
            t = self.peek()
            if t and t[0] in ("PLUS", "MINUS"):
                op = self.consume()[1]
                right = self.parse_term()
                node = (op, node, right)
                continue
            break
        return node

    def parse_term(self):
        node = self.parse_factor()
        while True:
            t = self.peek()
            if t and t[0] in ("MULTIPLY", "DIVIDE"):
                op = self.consume()[1]
                right = self.parse_factor()
                node = (op, node, right)
                continue
            break
        return node

    def parse_factor(self):
        # parse unary + - and primary
        t = self.peek()
        if t is None:
            raise SyntaxError("Unexpected end of input")
        if t[0] == "PLUS":
            self.consume()
            return ("UNARY", "+", self.parse_factor())
        if t[0] == "MINUS":
            self.consume()
            return ("UNARY", "-", self.parse_factor())
        # primary
        if t[0] == "NUM":
            self.consume()
            return int(t[1])
        if t[0] == "STRING":
            self.consume()
            s = t[1]
            qi = None
            for i, ch in enumerate(s):
                if ch == '"' or ch == "'":
                    qi = i
                    break
            prefix = ""
            if qi is not None:
                prefix = s[:qi]
                lit = s[qi:]
            else:
                lit = s
            pl = prefix.lower()
            if "f" in pl:
                inner = lit[1:-1]
                return ("FSTRING", inner, prefix)
            # treat 're' prefix as a regex literal (compile at runtime)
            if pl == "re" or pl.startswith("re"):
                inner = lit[1:-1]
                return ("REGEX", inner)
            # treat single-letter 'r' as a raw string (preserve backslashes)
            if pl == "r":
                inner = lit[1:-1]
                return inner
            return ast.literal_eval(s)
        if t[0] == "TRUE":
            self.consume()
            return True
        if t[0] == "FALSE":
            self.consume()
            return False
        if t[0] == "NONE":
            self.consume()
            return None
        if t[0] == "LBRACKET":
            self.consume()
            items = []
            if self.peek() and self.peek()[0] != "RBRACKET":
                while True:
                    items.append(self.parse_expression())
                    if self.peek() and self.peek()[0] == "COMMA":
                        self.consume()
                        continue
                    break
            if not self.peek() or self.peek()[0] != "RBRACKET":
                raise SyntaxError("Expected ]")
            self.consume()
            node = ("LIST", items)
            return self._postfix(node)
        if t[0] == "IDENTIFIER":
            self.consume()
            node = ("VAR", t[1])
            return self._postfix(node)
        if t[0] == "LPAREN":
            self.consume()
            node = self.parse_expression()
            if not self.peek() or self.peek()[0] != "RPAREN":
                raise SyntaxError("Expected )")
            self.consume()
            return self._postfix(node)
        if t[0] == "NOT":
            self.consume()
            return ("NOT", self.parse_factor())
        raise SyntaxError(f"Unexpected token: {t}")

    def _postfix(self, node):
        # handle calls, attribute access, indexing
        while True:
            t = self.peek()
            if not t:
                break
            if t[0] == "LPAREN":
                self.consume()
                args = []
                if self.peek() and self.peek()[0] != "RPAREN":
                    while True:
                        args.append(self.parse_expression())
                        if self.peek() and self.peek()[0] == "COMMA":
                            self.consume()
                            continue
                        break
                if not self.peek() or self.peek()[0] != "RPAREN":
                    raise SyntaxError("Expected ) after call")
                self.consume()
                node = ("CALL", node, args)
                continue
            if t[0] == "DOT":
                self.consume()
                name = self.consume()
                if not name or name[0] != "IDENTIFIER":
                    raise SyntaxError("Expected attribute name after .")
                node = ("ATTR", node, name[1])
                continue
            if t[0] == "LBRACKET":
                self.consume()
                idx = self.parse_expression()
                if not self.peek() or self.peek()[0] != "RBRACKET":
                    raise SyntaxError("Expected ] after index")
                self.consume()
                node = ("INDEX", node, idx)
                continue
            break
        return node
