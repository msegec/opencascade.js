import clang.cindex
import re

from wasmGenerator.Common import SkipException, isAbstractClass, getMethodOverloadPostfix
from filter.filterClasses import filterClass
from filter.filterMethodOrProperties import filterMethodOrProperty
from typing import List

def merge(sep: str, *strings: List[str]):
  return sep.join(strings)

def pick(condition: bool, strTrue: str, strFalse: str):
  return strTrue if condition else strFalse

def indent(level: int):
  return " " * level * 2

def shouldProcessClass(child: clang.cindex.Cursor, occtBasePath: str):
  if child.get_definition() is None or not child == child.get_definition():
    return False

  if not filterClass(child):
    return False

  if (
    child.kind == clang.cindex.CursorKind.CLASS_DECL or
    child.kind == clang.cindex.CursorKind.STRUCT_DECL
  ) and not child.type.get_num_template_arguments() == -1:
    return False

  if (
    child.kind == clang.cindex.CursorKind.CLASS_DECL or
    child.kind == clang.cindex.CursorKind.STRUCT_DECL
  ):
    baseSpec = list(filter(lambda x: x.kind == clang.cindex.CursorKind.CXX_BASE_SPECIFIER and x.access_specifier == clang.cindex.AccessSpecifier.PUBLIC, child.get_children()))
    if len(baseSpec) > 1:
      print("cannot handle multiple base classes (" + child.spelling + ")")
      return False
    
    return True

  return False

builtInTypes = [ # according to https://en.cppreference.com/w/cpp/language/types
  # Integer types
  "int",
  "short", "short int", "signed short", "signed short int",
  "unsigned short", "unsigned short int",
  "int", "signed", "signed int",
  "unsigned", "unsigned int",
  "long", "long int", "signed long", "signed long int",
  "unsigned long", "unsigned long int",
  "long long", "long long int", "signed long long", "signed long long int",
  "unsigned long long", "unsigned long long int",
  # Boolean type
  "bool",
  # Character types
  "char",
  "signed char", "unsigned char",
  "wchar_t",
  "char16_t", "char32_t", "char8_t",
  # Floating point types
  "float", "double", "long double"
]

cStringTypes = [
  "const char *",
  "const char *const",
  "char *",
  "char *const",
]

def isCString(type):
  return type.get_canonical().spelling in cStringTypes

def unwrapElaborated(type):
  return type.get_named_type() if type.kind == clang.cindex.TypeKind.ELABORATED else type

def scopeSpelling(scope):
  if scope.kind == clang.cindex.CursorKind.CLASS_TEMPLATE:
    params = [x.spelling for x in scope.get_children() if x.kind in [
      clang.cindex.CursorKind.TEMPLATE_TYPE_PARAMETER,
      clang.cindex.CursorKind.TEMPLATE_NON_TYPE_PARAMETER,
      clang.cindex.CursorKind.TEMPLATE_TEMPLATE_PARAMETER,
    ]]
    return scope.spelling + "<" + ", ".join(params) + ">"
  return scope.type.spelling

def normalizeSpelling(spelling):
  return re.sub("(?<![\\w:])occ::handle<", "opencascade::handle<", spelling)

def qualifiedSpelling(type):
  inner = type
  while inner.kind in [clang.cindex.TypeKind.LVALUEREFERENCE, clang.cindex.TypeKind.RVALUEREFERENCE, clang.cindex.TypeKind.POINTER]:
    inner = inner.get_pointee()
  if not inner.kind == clang.cindex.TypeKind.ELABORATED:
    return type.spelling
  declaration = inner.get_named_type().get_declaration()
  scope = declaration.semantic_parent
  if (
    scope is None or
    scope.spelling == "" or
    not scope.kind in [clang.cindex.CursorKind.CLASS_DECL, clang.cindex.CursorKind.STRUCT_DECL, clang.cindex.CursorKind.CLASS_TEMPLATE] or
    not re.sub("^(const |volatile )+", "", inner.spelling) == declaration.spelling
  ):
    return type.spelling
  return re.sub("(?<![\\w:])" + re.escape(declaration.spelling) + "(?!\\w)", scopeSpelling(scope) + "::" + declaration.spelling, type.spelling, count=1)

def typeSpelling(type):
  return normalizeSpelling(qualifiedSpelling(type))

def isPublicConstructor(cursor):
  return (
    cursor.kind == clang.cindex.CursorKind.CONSTRUCTOR and
    cursor.access_specifier == clang.cindex.AccessSpecifier.PUBLIC and
    not cursor.is_deleted_method()
  )

def canonicalReferee(type):
  inner = type
  while inner.kind in [clang.cindex.TypeKind.LVALUEREFERENCE, clang.cindex.TypeKind.RVALUEREFERENCE]:
    inner = inner.get_pointee()
  return inner.get_canonical()

def qualifiedDeclarationName(type):
  scopes = []
  declaration = canonicalReferee(type).get_declaration()
  while declaration is not None and not declaration.kind == clang.cindex.CursorKind.TRANSLATION_UNIT:
    scopes.insert(0, declaration.spelling)
    declaration = declaration.semantic_parent
  return "::".join(x for x in scopes if not x.startswith("__"))

def isStringView(type):
  return (
    qualifiedDeclarationName(type) == "std::basic_string_view" and
    canonicalReferee(type).get_template_argument_type(0).spelling == "char"
  )

def optionalValueType(type):
  if not qualifiedDeclarationName(type) == "std::optional":
    return None
  return canonicalReferee(type).get_template_argument_type(0)

def unsupportedType(type):
  name = qualifiedDeclarationName(type)
  if name == "std::variant" or (name == "std::basic_string_view" and not isStringView(type)):
    return type.spelling
  value = optionalValueType(type)
  if value is not None and (
    value.spelling.startswith("std::") or
    not (value.spelling in builtInTypes or value.kind in [clang.cindex.TypeKind.RECORD, clang.cindex.TypeKind.ENUM])
  ):
    return type.spelling
  return None

def signatureTypes(method):
  if method.kind == clang.cindex.CursorKind.FIELD_DECL:
    return [method.type]
  return ([method.result_type] if method.kind == clang.cindex.CursorKind.CXX_METHOD else []) + [x.type for x in method.get_arguments()]

def unsupportedTypeMessage(theClass, method):
  unsupported = [x for x in map(unsupportedType, signatureTypes(method)) if x is not None]
  if len(unsupported) == 0:
    return None
  return "Unsupported type " + unsupported[0] + ", skipping " + theClass.spelling + "::" + method.spelling

def isSupported(theClass, method):
  message = unsupportedTypeMessage(theClass, method)
  if message is not None:
    print(message)
  return message is None

def getClassTypeName(theClass, templateDecl = None):
  return templateDecl.spelling if templateDecl is not None else theClass.spelling

class Bindings:
  def __init__(self, typedefs, templateTypedefs, translationUnit):
    self.templateTypedefs = templateTypedefs
    self.translationUnit = translationUnit
    self.typedefs = typedefs
    self.templateSelfSpelling = None
    self.optionalTypes = set()

  def collectOptionalTypes(self, method):
    for type in signatureTypes(method):
      value = optionalValueType(type)
      if value is not None:
        self.optionalTypes.add(value.spelling)

  def getTypedefedTemplateTypeAsString(self, theTypeSpelling, templateDecl = None, templateArgs = None):
    if templateDecl is None:
      typedefType = self.typedefs.get(theTypeSpelling)
    else:
      templateType = self.replaceTemplateArgs(theTypeSpelling, templateArgs)
      rawTemplateType = templateType.replace("&", "").replace("const", "").strip()
      rawTypedefType = next((x for x in self.templateTypedefs if (normalizeSpelling(x.underlying_typedef_type.spelling) == rawTemplateType or normalizeSpelling(x.underlying_typedef_type.spelling) == "opencascade::" + rawTemplateType)), None)
      if rawTypedefType is not None:
        rawTypedefType = rawTypedefType.spelling
      elif rawTemplateType == self.templateSelfSpelling:
        rawTypedefType = templateDecl.spelling
      else:
        rawTypedefType = rawTemplateType
      typedefType = templateType.replace(rawTemplateType, rawTypedefType)
    return theTypeSpelling if typedefType is None else typedefType

  def replaceTemplateArgs(self, string, templateArgs = None):
    newString = string
    if templateArgs is None:
      return newString
    for key in templateArgs:
      p = re.compile("(\\W+|^)" + key + "(\\W|$)")
      newString = p.sub("\\1" + normalizeSpelling(templateArgs[key].spelling) + "\\2", newString)
    return newString

  def processClass(self, theClass, templateDecl = None, templateArgs = None):
    output = ""
    if templateDecl is not None:
      self.templateSelfSpelling = self.replaceTemplateArgs(scopeSpelling(theClass), templateArgs)
    isAbstract = isAbstractClass(theClass, self.translationUnit)
    if not isAbstract:
      output += self.processSimpleConstructor(theClass)
    for method in theClass.get_children():
      if not filterMethodOrProperty(theClass, method):
        continue
      try:
        if method.access_specifier == clang.cindex.AccessSpecifier.PUBLIC and method.kind in [clang.cindex.CursorKind.CXX_METHOD, clang.cindex.CursorKind.FIELD_DECL] and not method.spelling.startswith("operator"):
          message = unsupportedTypeMessage(theClass, method)
          if message is not None:
            raise SkipException(message)
          self.collectOptionalTypes(method)
        output += self.processMethodOrProperty(theClass, method, templateDecl, templateArgs)
      except SkipException as e:
        print(str(e))
    output += self.processFinalizeClass()
    if not isAbstract:
      try:
        output += self.processOverloadedConstructors(theClass, None, templateDecl, templateArgs)
      except SkipException as e:
        print(str(e))
    return output

class EmbindBindings(Bindings):
  def __init__(
    self,
    typedefs, templateTypedefs,
    translationUnit
  ):
    super().__init__(typedefs, templateTypedefs, translationUnit)

  def processClass(self, theClass, templateDecl = None, templateArgs = None):
    output = ""
    className = getClassTypeName(theClass, templateDecl)
    if className == "":
      className = theClass.type.spelling

    baseSpec = list(filter(lambda x: x.kind == clang.cindex.CursorKind.CXX_BASE_SPECIFIER and x.access_specifier == clang.cindex.AccessSpecifier.PUBLIC, theClass.get_children()))

    if len(baseSpec) > 0 and not baseSpec[0].type.get_canonical().spelling.startswith("std::"):
      baseClassBinding = ", base<" + self.replaceTemplateArgs(baseSpec[0].type.spelling, templateArgs) + ">"
    else:
      baseClassBinding = ""

    output += "EMSCRIPTEN_BINDINGS(" + (theClass.spelling if templateDecl is None else templateDecl.spelling) + ") {\n"
    output += "  class_<" + className + baseClassBinding + ">(\"" + className + "\")\n"

    output += super().processClass(theClass, templateDecl, templateArgs)
    output += "".join(map(lambda x: "  register_optional<" + x + ">();\n", sorted(self.optionalTypes)))

    output += "}\n\n"

    # Epilog
    nonPublicDestructor = any(x.kind == clang.cindex.CursorKind.DESTRUCTOR and not x.access_specifier == clang.cindex.AccessSpecifier.PUBLIC for x in theClass.get_children())
    deletes = [x for x in theClass.get_children() if x.spelling == "operator delete"]
    noUsualDelete = len(deletes) > 0 and not any(x.access_specifier == clang.cindex.AccessSpecifier.PUBLIC and len(list(x.get_arguments())) == 1 for x in deletes)
    if nonPublicDestructor or noUsualDelete:
      output += "namespace emscripten { namespace internal { template<> void raw_destructor<" + className + ">(" + className + "* ptr) { /* do nothing */ } } }\n"
    return output

  def processFinalizeClass(self):
    return "  ;\n"

  def processSimpleConstructor(self, theClass):
    output = ""
    children = list(theClass.get_children())
    constructors = list(filter(lambda x: x.kind == clang.cindex.CursorKind.CONSTRUCTOR, children))

    if len(constructors) == 0:
      output += "    .constructor<>()\n"
      return output
    publicConstructors = list(filter(isPublicConstructor, children))
    if len(publicConstructors) == 0 or len(publicConstructors) > 1:
      return output
    standardConstructor = publicConstructors[0]
    if not standardConstructor:
      return output

    argTypesBindings = ", ".join(list(map(lambda x: typeSpelling(x.type), list(standardConstructor.get_arguments()))))
    
    output += "    .constructor<" + argTypesBindings + ">()\n"
    return output

  def getSingleArgumentBinding(self, argNames = True, isConstructor = False, templateDecl = None, templateArgs = None):
    def f(arg):
      argChildren = list(arg.get_children())
      argBinding = ""
      hasDefaultValue = any(x.spelling == "=" for x in list(arg.get_tokens()))
      isArray = not hasDefaultValue and len(argChildren) > 1 and argChildren[1].kind == clang.cindex.CursorKind.INTEGER_LITERAL
      changed = False
      if isArray:
        const = "const " if list(arg.get_tokens())[0].spelling == "const" else ""
        arrayCount = list(argChildren[1].get_tokens())[0].spelling
        argBinding = const + argChildren[0].type.spelling + " (&" + (arg.spelling if argNames else "") + ")[" + arrayCount + "]"
        changed = True
      else:
        typename = self.getTypedefedTemplateTypeAsString(typeSpelling(arg.type), templateDecl, templateArgs)
        if arg.type.kind == clang.cindex.TypeKind.LVALUEREFERENCE:
          tokenList = list(arg.get_tokens())
          isConstRef = len(tokenList) > 0 and tokenList[0].spelling == "const"
          if not isConstRef:
            if typename[-2] == "*" or "".join(typename.rsplit("&", 1)).strip() in ["Standard_Boolean", "Standard_Real", "Standard_Integer", "bool"]: # types that can be copied
              typename = "".join(typename.rsplit("&", 1))
              changed = True
            else:
              if isConstructor:
                typename = typename
                changed = True
              else:
                typename = "const " + typename
                changed = True
        argBinding = typename + ((" " + arg.spelling) if argNames else "")
      return [argBinding, changed]
    return f

  def processMethodOrProperty(self, theClass, method, templateDecl = None, templateArgs = None):
    output = ""
    className = getClassTypeName(theClass, templateDecl)
    if className == "":
      className = theClass.type.spelling
    if method.access_specifier == clang.cindex.AccessSpecifier.PUBLIC and method.kind == clang.cindex.CursorKind.CXX_METHOD and not method.spelling.startswith("operator"):
      [overloadPostfix, numOverloads] = getMethodOverloadPostfix(theClass, method)

      def needsWrapper(type):
        return (
          type.kind == clang.cindex.TypeKind.LVALUEREFERENCE and (
            type.get_pointee().get_canonical().spelling in builtInTypes or
            unwrapElaborated(type.get_pointee()).kind == clang.cindex.TypeKind.ENUM or
            unwrapElaborated(type.get_pointee()).kind == clang.cindex.TypeKind.POINTER or (
              theClass.kind == clang.cindex.CursorKind.CLASS_TEMPLATE and
              type.get_pointee().spelling in templateArgs and
              templateArgs[type.get_pointee().spelling].get_canonical().spelling in builtInTypes
            )
          ) or (
            type.get_canonical().kind == clang.cindex.TypeKind.POINTER and 
            isCString(type)
          ) or
          isStringView(type)
        )

      args = list(method.get_arguments())
      argsNeedingWrapper = list(map(lambda arg: needsWrapper(arg.type), args))
      returnNeedsWrapper = needsWrapper(method.result_type)
      if any(argsNeedingWrapper) or returnNeedsWrapper:
        def replaceTemplateArgs(x):
          if templateArgs is not None and args[x[0]].type.get_pointee().spelling.replace("const ", "") in templateArgs:
            return args[x[0]].type.spelling.replace(args[x[0]].type.get_pointee().spelling.replace("const ", ""), templateArgs[args[x[0]].type.get_pointee().spelling.replace("const ", "")].spelling)
          else:
            return self.replaceTemplateArgs(typeSpelling(args[x[0]].type), templateArgs)
        def getArgName(x):
          return pick(
            not args[x[0]].spelling == "",
            args[x[0]].spelling,
            f"argNo{str(x[0])}"
          )
        def getArgTypeName(type):
          if templateArgs is not None and type.get_pointee().spelling.replace("const ", "") in templateArgs:
            return type.get_pointee().spelling.replace(type.get_pointee().spelling.replace("const ", ""), templateArgs[type.get_pointee().spelling.replace("const ", "")].spelling)
          else:
            return typeSpelling(type.get_pointee())
        classTypeName = getClassTypeName(theClass, templateDecl)
        wrappedParamTypes = merge(", ", *map(lambda x:
          pick(
            x[1],
            "emscripten::val",
            replaceTemplateArgs(x)
          ),
          enumerate(argsNeedingWrapper)
        ))
        wrappedParamTypesAndNames = merge(", ", *map(lambda x:
          pick(
            x[1],
            f"emscripten::val {getArgName(x)}",
            f"{replaceTemplateArgs(x)} {getArgName(x)}",
          ), enumerate(argsNeedingWrapper)))
        def needsStringCopy(x):
          return x[1] and isCString(args[x[0]].type) and (
            not args[x[0]].type.get_canonical().get_pointee().is_const_qualified() or
            args[x[0]].type.is_const_qualified()
          )
        def generateGetReferenceValue(x):
          if x[1] and isStringView(args[x[0]].type):
            return f"{indent(4)}std::string str_{getArgName(x)} = {getArgName(x)}.as<std::string>();\n"
          elif needsStringCopy(x):
            return f"{indent(4)}std::string str_{getArgName(x)} = {getArgName(x)}.isNull() ? std::string() : {getArgName(x)}.as<std::string>();\n"
          elif x[1] and not isCString(args[x[0]].type):
            return (
              merge("",
                indent(4),
                "auto ref_",
                pick(not args[x[0]].spelling == "",
                  args[x[0]].spelling,
                  f"argNo{str(x[0])}"
                ),
                f" = getReferenceValue<{getArgTypeName(args[x[0]].type)}>({getArgName(x)});\n"
              )
            )
          else:
            return ""
        def generateUpdateReferenceValue(x):
          if x[1] and not isCString(args[x[0]].type) and not isStringView(args[x[0]].type):
            return  f"{indent(4)}updateReferenceValue<{getArgTypeName(args[x[0]].type)}>({getArgName(x)}, ref_{getArgName(x)});\n"
          else:
            return ""
        def generateInvocationArgs(x):
          if x[1]:
            if isStringView(args[x[0]].type):
              return f"std::string_view(str_{getArgName(x)})"
            elif not isCString(args[x[0]].type):
              return f"ref_{getArgName(x)}"
            else:
              if needsStringCopy(x):
                return f"{getArgName(x)}.isNull() ? nullptr : str_{getArgName(x)}.data()"
              else:
                return f"{getArgName(x)}.isNull() ? nullptr : {getArgName(x)}.as<std::string>().c_str()"
          else:
            return getArgName(x)
        resultTypeSpelling = \
          pick(returnNeedsWrapper, "emscripten::val", self.getTypedefedTemplateTypeAsString(typeSpelling(method.result_type), templateDecl, templateArgs))
        functionBindingHead = \
          merge("",
            "\n",
            indent(3),
            f"(({resultTypeSpelling} (*)(",
            pick(not method.is_static_method(), f"{classTypeName}&", ""),
            pick(not method.is_static_method() and len(args) > 0, ", ", ""),
            wrappedParamTypes,
            "))",
            merge("",
              "[](",
              pick(not method.is_static_method(), f"{classTypeName}& that", ""),
              pick(not method.is_static_method() and len(args) > 0, ", ", ""),
              wrappedParamTypesAndNames,
              ")",
            ),
            f" -> {resultTypeSpelling} {{\n",
            merge("", *map(lambda x: generateGetReferenceValue(x), enumerate(argsNeedingWrapper))),
          )
        functionBindingBody = \
          merge("",
            indent(4),
            pick(
              not method.result_type.spelling == "void",
              merge("",
                pick(not isCString(method.result_type) and (method.result_type.is_const_qualified() or method.result_type.get_pointee().is_const_qualified()), "const ", ""),
                "auto",
                pick(not isCString(method.result_type) and method.result_type.kind == clang.cindex.TypeKind.LVALUEREFERENCE, "& ", " "),
                "ret = ",
              ),
              ""
            ),
            merge("",
              pick(not method.is_static_method(), "that.", f"{className}::"),
              f'{method.spelling}({merge(", ", *map(lambda x: generateInvocationArgs(x), enumerate(argsNeedingWrapper)))})',
            ),
            ";\n",
            merge("", *map(lambda x: generateUpdateReferenceValue(x), enumerate(argsNeedingWrapper))),
            pick(
              method.result_type.spelling == "void",
              "",
              pick(
                returnNeedsWrapper,
                pick(
                  method.result_type.kind == clang.cindex.TypeKind.POINTER,
                  merge("",
                    indent(4),
                    "return ret == nullptr ? emscripten::val::null() : emscripten::val(static_cast<",
                      pick(isCString(method.result_type), "std::string", self.getTypedefedTemplateTypeAsString(typeSpelling(method.result_type), templateDecl, templateArgs)),
                    ">(ret));\n",
                  ),
                  f"{indent(4)}return emscripten::val({pick(isStringView(method.result_type), 'std::string(ret)', 'ret')});\n",
                ),
                f"{indent(4)}return ret;\n",
              ),
            ),
          )
        functionBinding = \
          merge("",
            functionBindingHead,
            functionBindingBody,
            f"{indent(3)}}}\n",
            f"{indent(2)})",
          )
      else:
        if numOverloads == 1:
          functionBinding = " &" + className + "::" + method.spelling
        else:
          functionBinding = merge("",
            " select_overload<",
            self.getTypedefedTemplateTypeAsString(typeSpelling(method.result_type), templateDecl, templateArgs),
            f'({merge(", ", *map(lambda x: self.getSingleArgumentBinding(True, True, templateDecl, templateArgs)(x)[0], list(method.get_arguments())))})',
            pick(method.is_const_method(), "const", ""),
            pick(not method.is_static_method(), f", {getClassTypeName(theClass, templateDecl)}", ""),
            f">(&{className}::{method.spelling})",
          )

      if method.is_static_method():
        functionCommand = "class_function"
      else:
        functionCommand = "function"

      output += f"{indent(2)}.{functionCommand}(\"{method.spelling}{overloadPostfix}\",{functionBinding}, allow_raw_pointers())\n"
    if method.access_specifier == clang.cindex.AccessSpecifier.PUBLIC and method.kind == clang.cindex.CursorKind.FIELD_DECL:
      if method.type.kind == clang.cindex.TypeKind.CONSTANTARRAY:
        print("Cannot handle array properties, skipping " + className + "::" + method.spelling)
      elif not method.type.get_pointee().kind == clang.cindex.TypeKind.INVALID:
        print("Cannot handle pointer properties, skipping " + className + "::" + method.spelling)
      else:
        output += f"{indent(2)}.property(\"{method.spelling}\", &{className}::{method.spelling})\n"
    return output

  def processOverloadedConstructors(self, theClass, children = None, templateDecl = None, templateArgs = None):
    output = ""
    if children is None:
      children = list(theClass.get_children())
    constructors = list(filter(isPublicConstructor, children))
    if len(constructors) == 1:
      return output
    constructorBindings = ""
    allOverloads = list(filter(isPublicConstructor, children))
    if len(allOverloads) == 1:
      raise Exception("Something weird happened")
    for constructor in filter(lambda x: filterMethodOrProperty(theClass, x) and isSupported(theClass, x), constructors):
      overloadPostfix = "" if (not len(allOverloads) > 1) else "_" + str(allOverloads.index(constructor) + 1)
      self.collectOptionalTypes(constructor)

      args = ", ".join(list(map(lambda x: ("std::string " + x.spelling) if isCString(x.type) or isStringView(x.type) else self.getSingleArgumentBinding(True, True, templateDecl, templateArgs)(x)[0], constructor.get_arguments())))
      argNames = ", ".join(list(map(lambda x: (x.spelling + ".c_str()") if isCString(x.type) else x.spelling, constructor.get_arguments())))
      argTypes = ", ".join(list(map(lambda x: "std::string" if isCString(x.type) or isStringView(x.type) else self.getSingleArgumentBinding(False, True, templateDecl, templateArgs)(x)[0], constructor.get_arguments())))

      name = getClassTypeName(theClass, templateDecl)
      constructorBindings += "    struct " + name + overloadPostfix + " : public " + name + " {\n"
      constructorBindings += "      " + name + overloadPostfix + "(" + args + ") : " + name + "(" + argNames + ") {}\n"
      constructorBindings += "    };\n"
      constructorBindings += "    class_<" + name + overloadPostfix + ", base<" + name + ">>(\"" + name + overloadPostfix + "\")\n"
      constructorBindings += "      .constructor<" + argTypes + ">()\n"
      constructorBindings += "    ;\n"

    output += constructorBindings
    return output

  def processEnum(self, theEnum):
    output = "EMSCRIPTEN_BINDINGS(" + theEnum.spelling + ") {\n"

    bindingsOutput = "  enum_<" + theEnum.spelling + ">(\"" + theEnum.spelling + "\")\n"
    enumChildren = list(theEnum.get_children())
    prefix = (theEnum.spelling + "::") if theEnum.is_scoped_enum() else ""
    for enumChild in enumChildren:
      bindingsOutput += "    .value(\"" + enumChild.spelling + "\", " + prefix + enumChild.spelling + ")\n"
    bindingsOutput += "  ;\n"
    output += bindingsOutput

    output += "}\n\n"
    return output

class TypescriptBindings(Bindings):
  def __init__(
    self,
    typedefs, templateTypedefs,
    translationUnit
  ):
    super().__init__(typedefs, templateTypedefs, translationUnit)
    self.imports = {}

    self.exports = []

  def processClass(self, theClass, templateDecl = None, templateArgs = None):
    output = ""
    baseSpec = list(filter(lambda x: x.kind == clang.cindex.CursorKind.CXX_BASE_SPECIFIER and x.access_specifier == clang.cindex.AccessSpecifier.PUBLIC, theClass.get_children()))
    baseClassDefinition = ""
    if len(baseSpec) > 0:
      if any(x in baseSpec[0].type.spelling for x in [":", "<"]):
        print("Unsupported character for base class \"" + baseSpec[0].type.spelling + "\" (" + theClass.spelling + ")")
      else:
        baseClassDefinition = " extends " + baseSpec[0].type.spelling
        # self.addImportIfWeHaveTo(baseSpec[0].type.spelling)

    name = getClassTypeName(theClass, templateDecl)
    output += "export declare class " + name + baseClassDefinition + " {\n"
    self.exports.append(name)

    output += super().processClass(theClass, templateDecl, templateArgs)
    return output

  def processFinalizeClass(self):
    output = ""
    output += "  delete(): void;\n"
    output += "}\n\n"
    return output

  def processSimpleConstructor(self, theClass):
    output = ""
    children = list(theClass.get_children())
    constructors = list(filter(lambda x: x.kind == clang.cindex.CursorKind.CONSTRUCTOR, children))

    if len(constructors) == 0:
      output += "  constructor();\n"
      return output
    publicConstructors = list(filter(isPublicConstructor, children))
    if len(publicConstructors) == 0 or len(publicConstructors) > 1:
      return output
    standardConstructor = publicConstructors[0]
    if not standardConstructor:
      return output

    argsTypescriptDef = ", ".join(list(map(lambda x: self.getTypescriptDefFromArg(x), list(standardConstructor.get_arguments()))))
    
    output += "  constructor(" + argsTypescriptDef + ")\n"
    return output

  def convertBuiltinTypes(self, typeName):
    if typeName in [
      "int",
      "int16_t",
      "unsigned",
      "uint32_t",
      "unsigned int",
      "unsigned long"
      "long",
      "long int",
      "unsigned short",
      "short",
      "short int",
      "float",
      "unsigned float",
      "double",
      "unsigned double"
    ]:
      return "number"

    if typeName in [
      "char",
      "unsigned char",
      "std::string",
      "std::string_view"
    ]:
      return "string"

    if typeName in [
      "bool"
    ]:
      return "boolean"
    return typeName

  def getTypescriptDefFromResultType(self, res, templateDecl = None, templateArgs = None):
    value = optionalValueType(res)
    if value is not None:
      return self.getTypescriptDefFromResultType(value, templateDecl, templateArgs) + " | undefined"
    if not res.spelling == "void":
      typedefType = self.getTypedefedTemplateTypeAsString(typeSpelling(res).replace("&", "").replace("const", "").replace("*", "").strip(), templateDecl, templateArgs)
      resTypeName = typedefType.replace("&", "").replace("const", "").replace("*", "").strip()
      resTypeName = self.convertBuiltinTypes(resTypeName)
    else:
      resTypedefType = res.spelling.replace("&", "").replace("const", "").replace("*", "").strip()
      resTypeName = resTypedefType
    if resTypeName == "" or "(" in resTypeName or ":" in resTypeName or "<" in resTypeName:
      print("could not generate proper types for type name '" + resTypeName + "', using 'any' instead.")
      resTypeName = "any"
    return resTypeName

  def getTypescriptDefFromArg(self, arg, suffix = "", templateDecl = None, templateArgs = None):
    argTypeName = self.getTypedefedTemplateTypeAsString(typeSpelling(arg.type).replace("&", "").replace("const", "").replace("*", "").strip(), templateDecl, templateArgs)
    argTypeName = argTypeName.replace("&", "").replace("const", "").replace("*", "").strip()
    argTypeName = self.convertBuiltinTypes(argTypeName)
    if optionalValueType(arg.type) is not None:
      argTypeName = self.getTypescriptDefFromResultType(optionalValueType(arg.type), templateDecl, templateArgs) + " | undefined"
    elif argTypeName == "" or "(" in argTypeName or ":" in argTypeName:
      print("could not generate proper types for type name '" + argTypeName + "', using 'any' instead.")
      argTypeName = "any"

    argname = (arg.spelling if not arg.spelling == "" else ("a" + str(suffix)))
    if argname in ["var", "with", "super"]:
      argname += "_"
    return argname + ": " + argTypeName

  def processMethodOrProperty(self, theClass, method, templateDecl = None, templateArgs = None):
    output = ""
    if method.access_specifier == clang.cindex.AccessSpecifier.PUBLIC and method.kind == clang.cindex.CursorKind.CXX_METHOD and not method.spelling.startswith("operator"):
      [overloadPostfix, numOverloads] = getMethodOverloadPostfix(theClass, method)

      args = ", ".join(list(map(lambda x: self.getTypescriptDefFromArg(x[1], x[0], templateDecl, templateArgs), enumerate(method.get_arguments()))))
      returnType = self.getTypescriptDefFromResultType(method.result_type, templateDecl, templateArgs)

      output += "  " + ("static " if method.is_static_method() else "") + method.spelling + overloadPostfix + "(" + args + "): " + returnType + ";\n"
    return output

  def processOverloadedConstructors(self, theClass, children = None, templateDecl = None, templateArgs = None):
    output = ""
    if children is None:
      children = list(theClass.get_children())
    constructors = list(filter(isPublicConstructor, children))
    if len(constructors) == 1:
      return output

    constructorTypescriptDef = ""
    allOverloadedConstructors = []

    for constructor in filter(lambda x: filterMethodOrProperty(theClass, x) and isSupported(theClass, x), constructors):
      [overloadPostfix, numOverloads] = getMethodOverloadPostfix(theClass, constructor, children)

      argsTypescriptDef = ", ".join(list(map(lambda x: self.getTypescriptDefFromArg(x, "", templateDecl, templateArgs), list(constructor.get_arguments()))))
      name = getClassTypeName(theClass, templateDecl)
      constructorTypescriptDef += "  export declare class " + name + overloadPostfix + " extends " + name + " {\n"
      constructorTypescriptDef += "    constructor(" + argsTypescriptDef + ");\n"
      constructorTypescriptDef += "  }\n\n"
      allOverloadedConstructors.append(name + overloadPostfix)
    output += constructorTypescriptDef
    self.exports.extend(allOverloadedConstructors)
    return output

  def processEnum(self, theEnum):
    output = ""
    bindingsOutput = "export declare type " + theEnum.spelling + " = {\n"
    for enumChild in list(theEnum.get_children()):
      bindingsOutput += "  " + enumChild.spelling + ": {};\n"
    bindingsOutput += "}\n\n"
    output += bindingsOutput
    self.exports.append(theEnum.spelling)
    return output
