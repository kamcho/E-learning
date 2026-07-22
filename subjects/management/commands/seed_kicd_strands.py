"""
Seed Grade-Specific Strand and SubStrand data aligned to KICD CBC.
"""

from django.core.management.base import BaseCommand
from django.utils.text import slugify
from subjects.models import Subject, Strand, SubStrand

def get_curriculum(subject_name, grade_slug):
    # Determine grade band or specific grade
    is_pp = grade_slug in ['pp1', 'pp2']
    is_lower = grade_slug in ['grade-1', 'grade-2', 'grade-3']
    is_upper = grade_slug in ['grade-4', 'grade-5', 'grade-6']
    is_junior = grade_slug in ['grade-7', 'grade-8', 'grade-9']
    is_senior = grade_slug in ['grade-10', 'grade-11', 'grade-12']
    
    # 1. Mathematics / Mathematical Activities
    if subject_name in ['Mathematical Activities', 'Mathematics']:
        if is_pp:
            return [
                ('Numbers', ['Counting', 'Number Recognition', 'Simple Addition Concepts']),
                ('Measurement', ['Comparing Sizes', 'Comparing Weights', 'Time Concepts (Day/Night)']),
                ('Geometry', ['Recognizing Shapes', 'Patterns']),
            ]
        elif is_lower:
            if grade_slug == 'grade-1':
                return [
                    ('Numbers', ['Number Concept (1-100)', 'Whole Numbers', 'Addition (single digit)', 'Subtraction (single digit)', 'Fractions (Half)']),
                    ('Measurement', ['Length', 'Mass', 'Capacity', 'Time', 'Money']),
                    ('Geometry', ['Lines', 'Basic Shapes']),
                ]
            elif grade_slug == 'grade-2':
                return [
                    ('Numbers', ['Number Concept (1-1000)', 'Whole Numbers', 'Addition (double digit)', 'Subtraction (double digit)', 'Multiplication (introduction)', 'Division (introduction)', 'Fractions (Half and Quarter)']),
                    ('Measurement', ['Length', 'Mass', 'Capacity', 'Time', 'Money']),
                    ('Geometry', ['Lines', '2D Shapes']),
                ]
            else: # grade-3
                return [
                    ('Numbers', ['Number Concept (1-10000)', 'Whole Numbers', 'Addition (three digit)', 'Subtraction (three digit)', 'Multiplication', 'Division', 'Fractions (Half, Quarter, Eighth)']),
                    ('Measurement', ['Length', 'Mass', 'Capacity', 'Time', 'Money']),
                    ('Geometry', ['Lines', '3D Shapes']),
                ]
        elif is_upper:
            if grade_slug == 'grade-4':
                return [
                    ('Numbers', ['Whole Numbers (up to 100000)', 'Factors', 'Fractions', 'Decimals', 'Addition and Subtraction', 'Multiplication and Division']),
                    ('Measurement', ['Length', 'Area', 'Capacity', 'Time', 'Money']),
                    ('Geometry', ['Angles', '3D Shapes']),
                    ('Algebra', ['Algebraic Expressions']),
                    ('Data Handling', ['Data Collection', 'Pictographs']),
                ]
            elif grade_slug == 'grade-5':
                return [
                    ('Numbers', ['Whole Numbers (up to 1000000)', 'Factors and Multiples', 'Fractions', 'Decimals', 'Percentages', 'Addition and Subtraction', 'Multiplication and Division']),
                    ('Measurement', ['Length', 'Area', 'Volume', 'Capacity', 'Time', 'Money']),
                    ('Geometry', ['Angles', 'Position and Direction']),
                    ('Algebra', ['Linear Equations']),
                    ('Data Handling', ['Bar Charts']),
                ]
            else: # grade-6
                return [
                    ('Numbers', ['Whole Numbers (up to 10000000)', 'Factors and Multiples', 'Fractions', 'Decimals', 'Percentages', 'Ratios', 'Addition and Subtraction', 'Multiplication and Division']),
                    ('Measurement', ['Length', 'Area', 'Volume', 'Capacity', 'Time', 'Money']),
                    ('Geometry', ['Angles', 'Geometrical Construction']),
                    ('Algebra', ['Linear Equations and Inequalities']),
                    ('Data Handling', ['Line Graphs', 'Mean, Median and Mode']),
                ]
        elif is_junior:
            return [
                ('Numbers', [f'Integers ({grade_slug.title()})', 'Fractions and Decimals', 'Squares and Square Roots', 'Rates, Ratios, Percentages']),
                ('Measurement', ['Pythagoras Theorem', 'Area of Quadrilaterals', 'Volume of Prisms']),
                ('Geometry', ['Angles and Parallel Lines', 'Geometrical Constructions']),
                ('Algebra', ['Algebraic Expressions', 'Linear Equations', 'Linear Inequalities']),
                ('Data Handling', ['Data Collection and Presentation', 'Probability']),
            ]
        elif is_senior:
            return [
                ('Algebra & Numbers', [f'Indices and Logarithms ({grade_slug.title()})', 'Sequences and Series', 'Surds']),
                ('Geometry & Trigonometry', ['Trigonometric Ratios', 'Vectors', 'Three Dimensional Geometry']),
                ('Calculus & Statistics', ['Differentiation', 'Integration', 'Probability', 'Measures of Dispersion']),
            ]

    # 2. English / Language Activities
    if subject_name in ['Language Activities', 'English']:
        if is_pp:
            return [
                ('Listening and Speaking', ['Pre-listening Skills', 'Oral Communication', 'Vocabulary']),
                ('Reading', ['Pre-reading Skills', 'Book Handling', 'Visual Discrimination']),
                ('Writing', ['Pre-writing Skills', 'Pattern Writing']),
            ]
        elif is_lower:
            return [
                ('Listening and Speaking', [f'Greetings and Self-introduction ({grade_slug.title()})', 'Pronunciation', 'Oral Comprehension']),
                ('Reading', ['Phonemic Awareness', 'Word Recognition', 'Reading Comprehension']),
                ('Grammar', ['Nouns and Pronouns', 'Verbs and Simple Tenses', 'Punctuation']),
                ('Writing', ['Spelling', 'Handwriting', 'Sentence Writing']),
            ]
        elif is_upper:
            return [
                ('Listening and Speaking', [f'Oral Presentation ({grade_slug.title()})', 'Dialogue and Conversation', 'Listening Comprehension']),
                ('Reading', ['Silent Reading', 'Vocabulary in Context', 'Comprehension Skills', 'Extensive Reading']),
                ('Grammar', ['Nouns and Pronouns', 'Tenses', 'Adjectives and Adverbs', 'Prepositions and Conjunctions']),
                ('Writing', ['Paragraph Writing', 'Creative Writing', 'Friendly Letters']),
            ]
        elif is_junior:
            return [
                ('Listening and Speaking', ['Active Listening', 'Public Speaking', 'Discussion and Debates']),
                ('Reading', ['Intensive Reading', 'Poetry Reading', 'Literary Texts Analysis']),
                ('Grammar', ['Parts of Speech', 'Sentence Structure', 'Active and Passive Voice', 'Direct and Indirect Speech']),
                ('Writing', ['Functional Writing', 'Expository Writing', 'Creative Writing']),
            ]
        elif is_senior:
            return [
                ('Listening and Speaking', ['Advanced Pronunciation', 'Oral Literature Analysis', 'Presentation Skills']),
                ('Reading & Comprehension', ['Critical Reading', 'Novel Study', 'Play Study', 'Poetry Analysis']),
                ('Grammar', ['Advanced Syntax', 'Clauses and Phrases', 'Subject-Verb Agreement']),
                ('Writing', ['Essay Writing (Argumentative/Narrative)', 'Report Writing', 'CV and Cover Letters']),
            ]

    # 3. Kiswahili
    if subject_name == 'Kiswahili':
        if is_lower:
            return [
                ('Kusikiliza na Kuzungumza', ['Maamkizi na Adabu', 'Matamshi Bora', 'Mazungumzo']),
                ('Kusoma', ['Kusoma Herufi na Silabi', 'Kusoma kwa Sauti', 'Ufahamu wa Kusokoma']),
                ('Sarufi', ['Nomino', 'Vitenzi vya Hali ya Sasa', 'Uakifishaji wa Kimsingi']),
                ('Kuandika', ['Imla', 'Hati Safi', 'Kuandika Sentensi']),
            ]
        elif is_upper:
            return [
                ('Kusikiliza na Kuzungumza', ['Kusikiliza kwa Ufahamu', 'Matamshi na Tahajia', 'Mjadala']),
                ('Kusoma', ['Kusoma kwa Kimya', 'Kusoma kwa Ziada', 'Ufahamu wa Kusoma']),
                ('Sarufi', ['Ngeli za Nomino', 'Nyakati na Hali', 'Viwakilishi na Vielezi', 'Viunganishi']),
                ('Kuandika', ['Insha ya Wasifu', 'Barua ya Kirafiki', 'Insha ya Methali']),
            ]
        elif is_junior:
            return [
                ('Kusikiliza na Kuzungumza', ['Kusikiliza kwa Ukinifu', 'Hotuba na Mazungumzo', 'Mashairi ya Kisasa']),
                ('Kusoma', ['Kusoma kwa Kina', 'Uchambuzi wa Riwaya/Tamthilia', 'Kusoma Magazeti na Makala']),
                ('Sarufi', ['Uchambuzi wa Ngeli', 'Unyambulishaji wa Vitenzi', 'Uainishaji wa Sentensi']),
                ('Kuandika', ['Insha ya Hotuba/Barua Rasmi', 'Uandishi wa Ripoti', 'Uandishi wa Ubunifu']),
            ]
        elif is_senior:
            return [
                ('Kusikiliza na Kuzungumza', ['Uchambuzi wa Fasihi Simulizi', 'Mjadala wa Kina', 'Lugha ya Kimawasiliano']),
                ('Kusoma', ['Uchambuzi wa Kidrama na Riwaya', 'Kusoma kwa Kina', 'Uchambuzi wa Mashairi ya Kale']),
                ('Sarufi', ['Sarufi Miundo', 'Uakifishaji wa Kina', 'Mnyambuliko wa Juu wa Vitenzi']),
                ('Kuandika', ['Insha za Kitaaluma', 'Wasifu Kazi (CV)', 'Insha za Hoja']),
            ]

    # 4. Sciences (Environmental, Integrated Science, Biology, Chemistry, Physics)
    if subject_name in ['Environmental Activities', 'Integrated Science', 'Biology', 'Chemistry', 'Physics']:
        if is_pp or (subject_name == 'Environmental Activities' and is_lower):
            return [
                ('Natural Environment', ['Soil and Water Conservation', 'Weather and Sky', 'Plants and Animals around us']),
                ('Social Environment', ['Our Family and School', 'Road Safety and Neighborhood']),
                ('Cleanliness and Hygiene', ['Personal Cleanliness', 'Safe Drinking Water', 'Waste Disposal']),
            ]
        elif is_upper or (subject_name == 'Integrated Science' and is_junior):
            return [
                ('Diversity of Matter', [f'States of Matter ({grade_slug.title()})', 'Mixtures and Separation', 'Acids, Bases and Indicators']),
                ('Living Things and Environment', ['Plants Structure and Function', 'Animals Adaptation', 'Human Digestive and Circulatory Systems']),
                ('Force and Energy', ['Forms of Energy', 'Effects of Force', 'Simple Circuits', 'Light Reflection']),
                ('Earth and Space Science', ['Soil Erosion Control', 'Weather Instruments', 'Solar System Models']),
            ]
        elif is_senior:
            if subject_name == 'Biology':
                return [
                    ('Cell Biology', ['Cell Structure', 'Cell Physiology', 'Microscope Operations']),
                    ('Human Physiology', ['Respiration and Gaseous Exchange', 'Excretion and Homeostasis', 'Genetics and Evolution']),
                    ('Plant Physiology', ['Photosynthesis and Nutrition', 'Transport in Plants', 'Reproduction in Plants']),
                ]
            elif subject_name == 'Chemistry':
                return [
                    ('Structure and Bonding', ['Atomic Structure and Periodic Table', 'Chemical Bonding', 'Structure and Properties of Solids']),
                    ('Inorganic Chemistry', ['Carbon and its Compounds', 'Nitrogen/Sulphur and their Compounds', 'Acids, Bases and Salts']),
                    ('Physical & Organic', ['Gas Laws', 'Electrochemistry', 'Alkanes/Alkenes/Alkynes', 'Alkanols/Alkanoic Acids']),
                ]
            elif subject_name == 'Physics':
                return [
                    ('Mechanics', ['Measurement', 'Force and Pressure', 'Linear Motion', 'Work, Energy, Power']),
                    ('Waves and Optics', ['Reflection and Refraction of Light', 'Wave Motion', 'Sound Waves']),
                    ('Electricity & Magnetism', ['Electrostatics', 'Current Electricity', 'Magnetism', 'Electromagnetism']),
                ]

    # 5. Humanities & Social Sciences (Social Studies, Geography, History, Community Service Learning)
    if subject_name in ['Social Studies', 'Geography', 'History and Citizenship', 'Community Service Learning']:
        if is_upper or (subject_name == 'Social Studies' and is_junior):
            return [
                ('Physical Environment', ['Maps and Compass Directions', 'Physical Features and Weather', 'Climate and Vegetation']),
                ('People and Population', ['Migrations of Communities', 'Population Distribution', 'Cultural Heritage']),
                ('Resources & Economy', ['Agriculture and Forestry', 'Mining and Tourism', 'Trade and Transport']),
                ('Governance & Citizenship', ['Human Rights', 'Structure of Government', 'National Unity']),
            ]
        elif is_senior:
            if subject_name == 'Geography':
                return [
                    ('Physical Geography', ['The Earth and Solar System', 'Weather and Climate', 'Rocks and Minerals', 'Internal Land-forming Processes']),
                    ('Human & Economic Geography', ['Agriculture and Forestry', 'Mining and Fishing', 'Tourism and Wildlife', 'Industries']),
                    ('Practical Geography', ['Statistical Methods', 'Map Work', 'Field Work']),
                ]
            elif subject_name == 'History and Citizenship':
                return [
                    ('Early History', ['Evolution of Man', 'Development of Agriculture', 'Migration of Kenyan Communities']),
                    ('Colonial Rule & Independence', ['Scramble and Partition of East Africa', 'Colonial Administration', 'Struggle for Independence']),
                    ('Constitution & Devolution', ['Constitution-making in Kenya', 'Structure of Devolved Government', 'National Integration']),
                ]
            elif subject_name == 'Community Service Learning':
                return [
                    ('Civic Responsibility', ['Community Needs Assessment', 'Project Design', 'Leadership Skills']),
                    ('Sustainability Projects', ['Waste Management and Recycling', 'Afforestation', 'Literacy Campaigns']),
                ]

    # 6. Agriculture & Nutrition / Hygiene & Nutrition
    if subject_name in ['Agriculture and Nutrition', 'Hygiene and Nutrition']:
        if is_lower: # Hygiene and Nutrition
            return [
                ('Personal Hygiene', ['Body Cleanliness', 'Care of Teeth', 'Grooming and Washing Clothes']),
                ('Foods and Nutrition', ['Balanced Diets', 'Healthy Eating Habits', 'Food Safety and Storage']),
                ('Safety and First Aid', ['Kitchen Safety', 'First Aid for Common Ailments', 'Medication Safety']),
            ]
        elif is_upper or is_junior: # Agriculture and Nutrition
            return [
                ('Environment & Soil Conservation', ['Soil Erosion Control', 'Water Harvesting', 'Agroforestry']),
                ('Crop Production', ['Seedbeds and Land Prep', 'Planting and Weeding', 'Pests and Diseases Control']),
                ('Animal Production', ['Livestock Feeds and Feeding', 'Domestic Animal Care', 'Poultry Keeping']),
                ('Nutrition & Meal Planning', ['Nutrient Sources', 'Meal Planning', 'Food Preservation Techniques']),
            ]

    # 7. Creative Arts / Creative Arts & Sports / Psychomotor & Creative Activities / Physical Education
    if subject_name in ['Creative Arts', 'Creative Arts and Sports', 'Psychomotor and Creative Activities', 'Physical Education']:
        if is_pp: # Psychomotor and Creative
            return [
                ('Gross Motor Skills', ['Balancing and Running', 'Kicking and Catching']),
                ('Fine Motor Skills', ['Paper Craft and Folding', 'Clay Modeling', 'Painting']),
                ('Music and Movement', ['Singing Games', 'Rhythmic Dance']),
            ]
        elif is_lower or is_upper: # Creative Arts
            return [
                ('Art and Craft', ['Drawing and Painting', 'Collage and Mosaic', 'Clay Work and Modeling', 'Leather and Basketry']),
                ('Music', ['Rhythm and Melody', 'Singing and Choral Verse', 'Playing Instruments']),
            ]
        elif is_junior: # Creative Arts and Sports
            return [
                ('Art and Design', ['Graphic Design', 'Puppetry', 'Visual Arts']),
                ('Music and Drama', ['Sol-fa Notation', 'Choral Performance', 'Stage Play']),
                ('Sports and Games', ['Athletics (Track & Field)', 'Ball Games', 'Gymnastics']),
            ]
        elif is_senior: # Physical Education
            return [
                ('Track and Field', ['Sprints and Relays', 'Long Jump', 'High Jump']),
                ('Ball Games', ['Football Tactics', 'Basketball Play', 'Volleyball/Netball Rules']),
                ('Water Safety', ['Swimming Strokes', 'Water Rescue and Safety']),
            ]

    # 8. Technical / Computer / Business Studies
    if subject_name in ['Pre-technical Studies', 'Computer Studies', 'Business Studies']:
        if is_junior: # Pre-technical Studies
            return [
                ('Materials and Tools', ['Workshop Safety Rules', 'Hand Tools Identification', 'Properties of Materials (Wood/Metal/Plastics)']),
                ('Technical Drawing', ['Geometrical Drawing', 'Isometric Projection', 'Freehand Sketching']),
                ('Mechanics and Electricity', ['Simple Machines', 'Basic Electrical Circuits', 'Electrical Safety']),
            ]
        elif is_senior:
            if subject_name == 'Computer Studies':
                return [
                    ('Computer Systems', ['Hardware Architecture', 'Operating Systems', 'System Maintenance and Troubleshooting']),
                    ('Application Software', ['Word Processing', 'Spreadsheets', 'Database Systems']),
                    ('Programming & Development', ['Algorithms and Flowcharts', 'Coding Basics', 'System Development Lifecycle']),
                ]
            elif subject_name == 'Business Studies':
                return [
                    ('Business & Entrepreneurship', ['Types of Business Ownership', 'Business Environment', 'Entrepreneurship Skills']),
                    ('Financial Accounting', ['Ledger Accounts', 'Balance Sheet and Trial Balance', 'Double Entry Bookkeeping']),
                    ('Economics', ['Demand and Supply Analysis', 'Market Structures', 'Productive Resources']),
                ]

    # 9. Religious Education / Religious Education Activities
    if subject_name in ['Religious Education', 'Religious Education Activities']:
        if is_pp: # Religious Education Activities
            return [
                ('God and Creation', ['Knowing God', 'God\'s Creation', 'Showing Thankfulness']),
                ('Holy Books and Prayers', ['Stories from Holy Writings', 'Simple Prayers']),
            ]
        elif is_lower or is_upper or is_junior: # Religious Education
            return [
                ('Holy Scriptures', ['Creation Narratives', 'Biblical/Quranic Stories', 'Life and Teachings of Prophets/Jesus']),
                ('Spiritual and Moral Values', ['Love and Compassion', 'Honesty and Integrity', 'Respect and Obedience']),
                ('Community Relations', ['Interpersonal Relationships', 'Helping the Needy', 'Living in Harmony']),
            ]

    # Default fallback curriculum mapping
    return [
        ('General Concepts', ['Overview', 'Introduction', 'Key Terminology']),
        ('Core Competencies', ['Practical Applications', 'Skill Development']),
    ]

def generate_unique_strand_slug(name, subject):
    base = f"{subject.id}-{slugify(name)}"
    base = base[:50]
    slug = base
    counter = 1
    while Strand.objects.filter(slug=slug).exists():
        suffix = f"-{counter}"
        slug = f"{base[:50-len(suffix)]}{suffix}"
        counter += 1
    return slug

def generate_unique_substrand_slug(name, strand):
    base = f"{strand.id}-{slugify(name)}"
    base = base[:50]
    slug = base
    counter = 1
    while SubStrand.objects.filter(slug=slug).exists():
        suffix = f"-{counter}"
        slug = f"{base[:50-len(suffix)]}{suffix}"
        counter += 1
    return slug

class Command(BaseCommand):
    help = 'Seed Strand and SubStrand models for KICD curriculum (Grade-Specific).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Delete existing Strand and SubStrand records before seeding.',
        )

    def handle(self, *args, **options):
        if options['clear']:
            deleted_sub = SubStrand.objects.all().delete()
            deleted_strand = Strand.objects.all().delete()
            self.stdout.write(self.style.WARNING(
                f'Cleared Strands and SubStrands (strands: {deleted_strand[0]}, substrands: {deleted_sub[0]}).'
            ))

        strands_created = 0
        substrands_created = 0
        
        subjects = Subject.objects.select_related('grade_level').all()
        if not subjects.exists():
            self.stdout.write(self.style.ERROR("No Subjects found in the database. Please run seed_kicd_curriculum first."))
            return

        for subject in subjects:
            grade_slug = subject.grade_level.slug
            curriculum_config = get_curriculum(subject.name, grade_slug)
            
            for strand_idx, (strand_name, substrands) in enumerate(curriculum_config, start=1):
                strand_obj = Strand.objects.filter(name=strand_name, subject=subject).first()
                if not strand_obj:
                    slug = generate_unique_strand_slug(strand_name, subject)
                    strand_obj = Strand.objects.create(
                        name=strand_name,
                        order=strand_idx,
                        slug=slug,
                        subject=subject,
                        is_active=True
                    )
                    strands_created += 1
                
                for sub_idx, sub_name in enumerate(substrands, start=1):
                    substrand_obj = SubStrand.objects.filter(name=sub_name, strand=strand_obj).first()
                    if not substrand_obj:
                        slug = generate_unique_substrand_slug(sub_name, strand_obj)
                        SubStrand.objects.create(
                            name=sub_name,
                            order=sub_idx,
                            slug=slug,
                            strand=strand_obj,
                            is_active=True
                        )
                        substrands_created += 1

        self.stdout.write(self.style.SUCCESS(
            f"Successfully completed grade-specific seeding:\n"
            f" - {strands_created} Strands created\n"
            f" - {substrands_created} SubStrands created"
        ))
