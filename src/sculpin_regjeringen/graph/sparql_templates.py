"""SPARQL templates for planned Sculpin tools."""

OPEN_HEARINGS_BY_DEPARTMENT = """
PREFIX scgov: <https://w3id.org/sculpin/government/regjeringen#>
PREFIX dcterms: <http://purl.org/dc/terms/>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>

SELECT ?document ?title ?deadline
WHERE {
  ?document a scgov:Consultation ;
            dcterms:title ?title ;
            scgov:responsibleDepartment ?department ;
            scgov:hasDeadline ?deadline .
  ?department skos:prefLabel ?departmentLabel .
  FILTER(CONTAINS(LCASE(STR(?departmentLabel)), LCASE(?departmentName)))
}
ORDER BY ?deadline
"""
