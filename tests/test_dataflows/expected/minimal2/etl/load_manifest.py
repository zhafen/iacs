raw_entity_first_data = {
    "examples/minimal2/minimal2.yaml": {
        "core_requirement": {
            "data": [
                {"description": "The main requirement the infrastructure must complete."},
                "requirement",
            ],
            "first_subrequirement": [
                {"description": "This requirement is a subrequirement of the core requirement, necessary to complete the core requirement.\n"},
                "requirement",
            ],
            "second_subrequirement": [
                {"description": "This requirement is also a subrequirement of the core requirement, necessary to complete the core requirement.\n"},
                "requirement",
            ],
        },
        "my_infrastructure": {
            "data": [
                {"description": "The overall infrastructure used to complete the core requirement."},
            ],
            "infrastructure_for_first_requirement": [
                {"description": "This solves the first requirement."},
                {"solution of": "core_requirement.first_subrequirement"},
            ],
            "infrastructure_for_second_requirement": [
                {"description": "This solves the second requirement."},
                {"solution of": "second_subrequirement"},
            ],
        },
    },
}
