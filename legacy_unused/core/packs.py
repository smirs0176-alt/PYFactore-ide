"""Пакеты языков для вкладки «Языки»: подсветка, шаблон Mystery.<расширение>, команда запуска."""
import re

from pyfactor import config
from pyfactor.core import langs


def _p(name, icon, ext, desc, kw, bi, cm, block, run, tpl):
    return dict(name=name, icon=icon, ext=ext, desc=desc, kw=set(kw.split()), bi=set(bi.split()), cm=cm,
                block=block, run=run, tpl=tpl)


PACKS = {
    "cs": _p("C#", "🟣", ".cs", "Язык Microsoft: игры на Unity, программы для Windows",
             "abstract as base bool break byte case catch char class const continue decimal default delegate do double else enum "
             "event false finally float for foreach if in int interface internal is lock long namespace new null object operator "
             "out override params private protected public readonly ref return short static string struct switch this throw true "
             "try typeof using virtual void while var async await record", "Console Math String List Dictionary Task Exception Random DateTime Array",
             "//", True, [["dotnet-script", "{f}"], ["csi", "{f}"]],
             'using System;\n\nclass Mystery\n{\n    static void Main()\n    {\n        Console.WriteLine("Привет из Mystery!");\n    }\n}\n'),
    "lua": _p("Lua", "🌙", ".lua", "Маленький быстрый язык для игр (Roblox, Love2D)",
              "and break do else elseif end false for function goto if in local nil not or repeat return then true until while",
              "print pairs ipairs table string math os io require tostring tonumber type setmetatable", "--", False,
              [["lua", "{f}"], ["lua5.4", "{f}"], ["luajit", "{f}"]],
              'print("Привет из Mystery!")\n\nlocal function square(x)\n    return x * x\nend\n\nprint(square(7))\n'),
    "ruby": _p("Ruby", "💎", ".rb", "Красивый язык для сайтов и скриптов",
               "alias and begin break case class def do else elsif end ensure false for if in module next nil not or rescue retry "
               "return self super then true unless until when while yield", "puts print require gets attr_accessor attr_reader each map select Array Hash String Integer",
               "#", False, [["ruby", "{f}"]], 'puts "Привет из Mystery!"\n3.times { |i| puts "Раз #{i}" }\n'),
    "go": _p("Go", "🐹", ".go", "Язык от Google: быстрые серверы и утилиты",
             "break case chan const continue default defer else fallthrough for func go goto if import interface map package range "
             "return select struct switch type var true false nil", "fmt string int float64 bool byte error len make append panic println Println",
             "//", True, [["go", "run", "{f}"]],
             'package main\n\nimport "fmt"\n\nfunc main() {\n\tfmt.Println("Привет из Mystery!")\n}\n'),
    "java": _p("Java", "☕", ".java", "Классика: Minecraft, Android, большие программы",
               "abstract assert boolean break byte case catch char class const continue default do double else enum extends final "
               "finally float for if implements import instanceof int interface long new package private protected public return "
               "short static super switch this throw throws try void volatile while true false null var record",
               "String System Math List Map ArrayList HashMap Scanner Integer Object Exception", "//", True, [["java", "{f}"]],
               'public class Mystery {\n    public static void main(String[] args) {\n        System.out.println("Привет из Mystery!");\n    }\n}\n'),
    "php": _p("PHP", "🐘", ".php", "Язык сайтов: WordPress и многое другое",
              "abstract and array as break case catch class clone const continue default do echo else elseif empty extends final "
              "finally fn for foreach function global if implements include interface isset match namespace new or print private "
              "protected public require return static switch throw trait try unset use var while yield true false null",
              "strlen count array_map str_replace date json_encode json_decode var_dump print_r", "//", True, [["php", "{f}"]],
              '<?php\n\necho "Привет из Mystery!\\n";\n'),
    "rust": _p("Rust", "🦀", ".rs", "Быстрый и безопасный язык для серьёзных программ",
               "as async await break const continue crate dyn else enum extern false fn for if impl in let loop match mod move mut "
               "pub ref return self Self static struct super trait true type unsafe use where while",
               "String Vec Option Result Some None Ok Err println print format vec Box i32 i64 u32 u64 f64 bool usize str", "//", True, [],
               'fn main() {\n    println!("Привет из Mystery!");\n}\n'),
    "cpp": _p("C++", "⚙️", ".cpp", "Мощный язык для игр и движков",
              "alignas auto bool break case catch char class const constexpr continue default delete do double else enum explicit "
              "extern false float for friend goto if inline int long namespace new noexcept nullptr operator private protected public "
              "return short signed sizeof static struct switch template this throw true try typedef typename union unsigned using "
              "virtual void volatile while", "std cout cin endl string vector map cerr printf include", "//", True, [],
              '#include <iostream>\n\nint main() {\n    std::cout << "Привет из Mystery!" << std::endl;\n    return 0;\n}\n'),
}
INSTALLED = set()
config.TEXT_EXT.update(p["ext"] for p in PACKS.values())


def install(pid):
    p = PACKS[pid]
    INSTALLED.add(pid)
    langs.LANG_BY_EXT[p["ext"]] = pid
    langs.LANG_NAMES[pid] = p["name"]
    langs.LANG_ICONS[pid] = p["icon"]


def uninstall(pid):
    INSTALLED.discard(pid)
    langs.LANG_BY_EXT.pop(PACKS[pid]["ext"], None)


def spans_pack(code, p):
    parts = [r"(?P<comment>%s.*)" % re.escape(p["cm"]), r'(?P<string>"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\')',
             r"(?P<number>\b\d[\d_.]*\b)", r"(?P<word>[A-Za-z_]\w*)"]
    if p["block"]:
        parts.insert(0, r"(?P<block>(?s:/\*.*?\*/))")
    out = []
    for m in re.finditer("|".join(parts), code):
        k, w = m.lastgroup, m.group()
        if k == "word":
            k = "kw" if w in p["kw"] else "bi" if w in p["bi"] else "func" if code[m.end():m.end() + 1] == "(" else "cls" if w[0].isupper() else None
        elif k == "block":
            k = "comment"
        if k:
            out.append((m.start(), m.end(), k))
    return out
