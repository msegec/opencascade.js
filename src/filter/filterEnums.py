def filterEnum(enum, additionalInfo=None):
  # libclang 20 spells unnamed enums "(unnamed enum at <path>)", which breaks the output file path
  if enum.spelling == "" or enum.is_anonymous():
    return False
  return True
