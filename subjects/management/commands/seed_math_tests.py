"""
Seed Mathematics quizzes/tests with questions and options for Grades 1, 6, and 12.
"""

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from subjects.models import Subject, Strand, SubStrand
from core.models import Quiz, Question, Option

User = get_user_model()

TESTS_DATA = [
    {
        'grade_slug': 'grade-1',
        'strand_name': 'Numbers',
        'substrand_name': 'Addition (single digit)',
        'title': 'Grade 1 Math Addition Quiz',
        'description': 'Practice adding single digit numbers.',
        'difficulty': 'Easy',
        'questions': [
            {
                'text': 'What is 1 + 1?',
                'options': [('2', True), ('3', False), ('4', False), ('5', False)]
            },
            {
                'text': 'What is 2 + 3?',
                'options': [('5', True), ('4', False), ('6', False), ('3', False)]
            },
            {
                'text': 'What is 4 + 2?',
                'options': [('6', True), ('5', False), ('7', False), ('8', False)]
            },
            {
                'text': 'What is 5 + 0?',
                'options': [('5', True), ('0', False), ('10', False), ('6', False)]
            },
            {
                'text': 'What is 3 + 4?',
                'options': [('7', True), ('6', False), ('8', False), ('9', False)]
            }
        ]
    },
    {
        'grade_slug': 'grade-6',
        'strand_name': 'Numbers',
        'substrand_name': 'Multiplication and Division',
        'title': 'Grade 6 Math Multiplication & Division Quiz',
        'description': 'Test your skills in multiplying and dividing numbers.',
        'difficulty': 'Medium',
        'questions': [
            {
                'text': 'What is 125 x 8?',
                'options': [('1000', True), ('900', False), ('1100', False), ('1200', False)]
            },
            {
                'text': 'Solve: 240 / 6.',
                'options': [('40', True), ('30', False), ('50', False), ('60', False)]
            },
            {
                'text': 'What is 15 x 15?',
                'options': [('225', True), ('200', False), ('250', False), ('150', False)]
            },
            {
                'text': 'What is 144 / 12?',
                'options': [('12', True), ('10', False), ('14', False), ('16', False)]
            },
            {
                'text': 'What is 70 x 6?',
                'options': [('420', True), ('400', False), ('450', False), ('380', False)]
            }
        ]
    },
    {
        'grade_slug': 'grade-12',
        'strand_name': 'Calculus & Statistics',
        'substrand_name': 'Integration',
        'title': 'Grade 12 Calculus Integration Quiz',
        'description': 'Test your knowledge of calculus and integration.',
        'difficulty': 'Hard',
        'questions': [
            {
                'text': 'Evaluate the integral of 2x dx from 0 to 3.',
                'options': [('9', True), ('6', False), ('3', False), ('18', False)]
            },
            {
                'text': 'What is the indefinite integral of 3x^2 dx?',
                'options': [('x^3 + C', True), ('3x^3 + C', False), ('x^2 + C', False), ('6x + C', False)]
            },
            {
                'text': 'Evaluate the integral of cos(x) dx.',
                'options': [('sin(x) + C', True), ('-sin(x) + C', False), ('tan(x) + C', False), ('-cos(x) + C', False)]
            },
            {
                'text': 'Evaluate the integral of 1/x dx (for x > 0).',
                'options': [('ln(x) + C', True), ('-1/x^2 + C', False), ('e^x + C', False), ('x + C', False)]
            },
            {
                'text': 'Evaluate the integral of e^x dx.',
                'options': [('e^x + C', True), ('e^(2x) + C', False), ('x*e^x + C', False), ('ln(x) + C', False)]
            }
        ]
    }
]

class Command(BaseCommand):
    help = 'Seed Mathematics quizzes/tests with questions and options for Grades 1, 6, and 12.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Delete seeded Quiz, Question, and Option records before seeding.',
        )

    def handle(self, *args, **options):
        # Fetch or create the creator user
        user = User.objects.filter(phone='0742134431').first()
        if not user:
            user = User.objects.first()
        if not user:
            user = User.objects.create_superuser(
                phone='0742134431',
                password='1234',
                first_name='System',
                last_name='Admin'
            )

        if options['clear']:
            quiz_titles = [q['title'] for q in TESTS_DATA]
            quizzes_to_del = Quiz.objects.filter(title__in=quiz_titles)
            questions_to_del = Question.objects.filter(quizzes__in=quizzes_to_del)
            
            deleted_opts = Option.objects.filter(question__in=questions_to_del).delete()
            deleted_quests = questions_to_del.delete()
            deleted_quizzes = quizzes_to_del.delete()
            
            self.stdout.write(self.style.WARNING(
                f"Cleared math test data (quizzes: {deleted_quizzes[0]}, questions: {deleted_quests[0]}, options: {deleted_opts[0]})."
            ))

        quizzes_seeded = 0
        questions_seeded = 0
        options_seeded = 0

        for quiz_data in TESTS_DATA:
            # Find subject
            subject = Subject.objects.filter(
                name='Mathematics',
                grade_level__slug=quiz_data['grade_slug']
            ).first()
            if not subject:
                self.stdout.write(self.style.ERROR(
                    f"Subject 'Mathematics' for grade '{quiz_data['grade_slug']}' not found."
                ))
                continue
            
            # Find strand
            strand = Strand.objects.filter(
                name=quiz_data['strand_name'],
                subject=subject
            ).first()
            if not strand:
                self.stdout.write(self.style.ERROR(
                    f"Strand '{quiz_data['strand_name']}' for subject '{subject}' not found."
                ))
                continue
            
            # Find sub-strand
            sub_strand = SubStrand.objects.filter(
                name=quiz_data['substrand_name'],
                strand=strand
            ).first()
            if not sub_strand:
                self.stdout.write(self.style.ERROR(
                    f"SubStrand '{quiz_data['substrand_name']}' for strand '{strand}' not found."
                ))
                continue
            
            # Create Quiz
            quiz_obj, created = Quiz.objects.get_or_create(
                title=quiz_data['title'],
                sub_strand=sub_strand,
                defaults={
                    'description': quiz_data['description'],
                    'difficulty': quiz_data['difficulty'],
                    'subject': subject,
                    'strand': strand,
                    'is_active': True,
                    'test_size': len(quiz_data['questions']),
                    'created_by': user
                }
            )
            
            if created:
                quizzes_seeded += 1
                self.stdout.write(self.style.SUCCESS(f"Created Quiz: {quiz_obj.title}"))
            else:
                self.stdout.write(self.style.WARNING(f"Quiz already exists: {quiz_obj.title}"))
            
            # Add Questions
            for q_idx, q_data in enumerate(quiz_data['questions'], start=1):
                question_obj, q_created = Question.objects.get_or_create(
                    quiz=q_data['text'],
                    sub_strand=sub_strand,
                    defaults={
                        'score': 2,
                        'difficulty': quiz_data['difficulty'],
                        'quiz_type': 'Multiple Choice',
                        'is_active': True
                    }
                )
                
                if q_created:
                    questions_seeded += 1
                    self.stdout.write(self.style.SUCCESS(f"  + Question: {question_obj.quiz}"))
                else:
                    self.stdout.write(f"  = Question exists: {question_obj.quiz}")
                
                # Link to Quiz
                quiz_obj.questions.add(question_obj)
                
                # Create Options
                for opt_text, is_correct in q_data['options']:
                    opt_obj, opt_created = Option.objects.get_or_create(
                        question=question_obj,
                        option=opt_text,
                        defaults={
                            'is_correct': is_correct,
                            'is_active': True
                        }
                    )
                    if opt_created:
                        options_seeded += 1

        self.stdout.write(self.style.SUCCESS(
            f"Successfully completed mathematics test seeding:\n"
            f" - {quizzes_seeded} Quiz records seeded\n"
            f" - {questions_seeded} Question records seeded\n"
            f" - {options_seeded} Option records seeded"
        ))
