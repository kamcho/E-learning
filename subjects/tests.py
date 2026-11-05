import json
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import Role
from subjects.curriculum_import import (
    CurriculumImportError,
    create_curriculum,
    parse_curriculum_text,
)

from subjects.forms import StrandForm, SubStrandForm
from subjects.models import Discipline, GradeLevel, Subject


class StrandFormTests(TestCase):
    def setUp(self):
        grade = GradeLevel.objects.create(
            name='Grade 1',
            slug='grade-1',
            level='Lower Primary',
        )
        discipline = Discipline.objects.create(
            name='Religious Education',
            slug='religious-education',
        )
        self.subject = Subject.objects.create(
            name='Religious Education Grade 1',
            slug='religious-education-grade-1',
            grade_level=grade,
            discipline=discipline,
        )

    def test_blank_slug_is_generated_from_strand_and_subject_names(self):
        form = StrandForm(data={
            'name': 'Creation',
            'order': 1,
            'subject': self.subject.pk,
        })

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(
            form.cleaned_data['slug'],
            'creation-religious-education-grade-1',
        )

    def test_strand_and_substrand_slug_inputs_use_the_standard_form_style(self):
        for form_class in (StrandForm, SubStrandForm):
            with self.subTest(form=form_class.__name__):
                widget = form_class().fields['slug'].widget
                self.assertEqual(widget.attrs.get('class'), 'form-input')
                self.assertEqual(
                    widget.attrs.get('placeholder'),
                    'Leave blank to auto-generate',
                )


class CurriculumImportTests(TestCase):
    def setUp(self):
        grade = GradeLevel.objects.create(
            name='Grade 1',
            slug='grade-1',
            level='Lower Primary',
        )
        discipline = Discipline.objects.create(
            name='Religious Education',
            slug='religious-education',
        )
        self.subject = Subject.objects.create(
            name='Religious Education Grade 1',
            slug='religious-education-grade-1',
            grade_level=grade,
            discipline=discipline,
        )

    def test_parse_curriculum_assigns_numbering_from_table_structure(self):
        client = Mock()
        client.chat.return_value = json.dumps([
            {
                'name': '1.0 Creation',
                'sub_strands': ['1.1 Self Awareness', '1.2 My Family'],
            },
            {
                'name': '2.0 The Holy Bible',
                'sub_strands': ['2.1 The Word of God'],
            },
        ])

        result = parse_curriculum_text(
            '| Strand | Sub-strand |\n| Creation | Self Awareness |',
            self.subject,
            client=client,
        )

        self.assertEqual(result[0]['name'], 'Creation')
        self.assertEqual(result[0]['order'], 1)
        self.assertEqual(result[0]['sub_strands'][0], {
            'name': 'Self Awareness',
            'order': 1,
        })
        self.assertIn('Religious Education Grade 1', client.chat.call_args.kwargs['user_prompt'])
        self.assertTrue(client.chat.call_args.kwargs['json_mode'])

    def test_invalid_ai_response_is_rejected(self):
        client = Mock()
        client.chat.return_value = 'not json'

        with self.assertRaises(CurriculumImportError):
            parse_curriculum_text('a curriculum table', self.subject, client=client)

    def test_parse_curriculum_accepts_json_object_with_strands(self):
        client = Mock()
        client.chat.return_value = json.dumps({
            'strands': [{
                'name': 'Creation',
                'sub_strands': ['Self Awareness'],
            }],
        })

        result = parse_curriculum_text('a curriculum table', self.subject, client=client)

        self.assertEqual(result[0]['name'], 'Creation')
        self.assertEqual(result[0]['sub_strands'][0]['name'], 'Self Awareness')

    def test_create_curriculum_creates_strands_and_sub_strands(self):
        curriculum = [{
            'name': 'Creation',
            'order': 1,
            'sub_strands': [{'name': 'Self Awareness', 'order': 1}],
        }]

        created = create_curriculum(self.subject, curriculum)

        self.assertEqual(created, (1, 1))
        self.assertEqual(self.subject.strands.get().slug, 'creation-religious-education-grade-1')
        self.assertEqual(
            self.subject.strands.get().sub_strands.get().name,
            'Self Awareness',
        )

    def test_create_curriculum_keeps_existing_entries_and_adds_missing_children(self):
        from subjects.models import Strand, SubStrand

        strand = Strand.objects.create(
            name='Creation',
            order=1,
            slug='creation-existing',
            subject=self.subject,
        )
        SubStrand.objects.create(
            name='Self Awareness',
            order=1,
            slug='self-awareness-existing',
            strand=strand,
        )
        curriculum = [{
            'name': 'Creation',
            'order': 1,
            'sub_strands': [
                {'name': 'Self Awareness', 'order': 1},
                {'name': 'My Family', 'order': 2},
            ],
        }]

        created = create_curriculum(self.subject, curriculum)

        self.assertEqual(created, (0, 1))
        self.assertEqual(self.subject.strands.count(), 1)
        self.assertEqual(strand.sub_strands.count(), 2)

    def test_subject_page_previews_before_importing_and_requires_admin(self):
        user_model = get_user_model()
        admin = user_model.objects.create_user(
            phone='0744444444',
            password='1234',
            role=Role.ADMIN,
            first_name='Curriculum',
            last_name='Admin',
        )
        url = reverse('subjects:subject_detail', kwargs={'slug': self.subject.slug})
        self.client.force_login(admin)
        with patch('subjects.curriculum_import.OpenAIClient') as openai_client:
            openai_client.return_value.chat.return_value = json.dumps([{
                'name': 'Creation',
                'sub_strands': ['Self Awareness'],
            }])
            response = self.client.post(url, {
                'action': 'parse_curriculum',
                'curriculum_text': 'Creation | Self Awareness',
            })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Review parsed curriculum')
        self.assertContains(response, 'Confirm and create curriculum')
        self.assertEqual(self.subject.strands.count(), 0)

        response = self.client.post(url, {
            'action': 'import_curriculum',
            'preview_token': response.context['curriculum_preview_token'],
        })
        self.assertRedirects(response, url)
        self.assertEqual(self.subject.strands.count(), 1)

    def test_manual_strand_creation_still_works(self):
        admin = get_user_model().objects.create_user(
            phone='0744444446',
            password='1234',
            role=Role.ADMIN,
            first_name='Curriculum',
            last_name='Admin',
        )
        self.client.force_login(admin)
        url = reverse('subjects:subject_detail', kwargs={'slug': self.subject.slug})

        response = self.client.post(url, {
            'action': 'create_strand',
            'name': 'Creation',
            'slug': '',
            'order': 1,
            'subject': self.subject.pk,
        })

        self.assertRedirects(response, url)
        self.assertEqual(
            self.subject.strands.get().slug,
            'creation-religious-education-grade-1',
        )

    def test_signed_preview_cannot_be_tampered_with(self):
        from django.core import signing
        from subjects.curriculum_import import PREVIEW_SALT, load_curriculum_preview

        token = signing.dumps([], salt=PREVIEW_SALT)
        with self.assertRaises(CurriculumImportError):
            load_curriculum_preview(token)

    def test_ai_preview_is_hidden_from_non_admins(self):
        user_model = get_user_model()
        teacher = user_model.objects.create_user(
            phone='0744444445',
            password='1234',
            role=Role.TEACHER,
            first_name='Teacher',
            last_name='User',
        )
        self.client.force_login(teacher)
        response = self.client.post(
            reverse('subjects:subject_detail', kwargs={'slug': self.subject.slug}),
            {'action': 'parse_curriculum', 'curriculum_text': 'curriculum'},
        )
        self.assertRedirects(response, reverse('core:landing'), fetch_redirect_response=False)
        self.assertEqual(self.subject.strands.count(), 0)


class CurriculumNameEditingTests(TestCase):
    def setUp(self):
        grade = GradeLevel.objects.create(
            name='Grade 6',
            slug='grade-6',
            level='Upper Primary',
        )
        discipline = Discipline.objects.create(
            name='Agriculture and Nutrition',
            slug='agriculture-and-nutrition',
        )
        self.subject = Subject.objects.create(
            name='Agriculture and Nutrition',
            slug='agriculture-and-nutrition-grade-6',
            grade_level=grade,
            discipline=discipline,
        )
        from subjects.models import Strand, SubStrand

        self.strand = Strand.objects.create(
            name='Crop Production',
            order=1,
            slug='crop-production-agriculture-and-nutrition-grade-6',
            subject=self.subject,
        )
        self.sub_strand = SubStrand.objects.create(
            name='Planting',
            order=1,
            slug='planting-crop-production',
            strand=self.strand,
        )
        self.admin = get_user_model().objects.create_user(
            phone='0744444450',
            password='1234',
            role=Role.ADMIN,
            first_name='Curriculum',
            last_name='Admin',
        )

    def test_admin_can_rename_subject_strand_and_sub_strand_without_changing_slugs(self):
        self.client.force_login(self.admin)
        name_changes = (
            (
                reverse('subjects:subject_detail', kwargs={'slug': self.subject.slug}),
                {'action': 'rename_subject', 'name': 'Agriculture and Nutrition Grade 6'},
                self.subject,
            ),
            (
                reverse('subjects:strand_detail', kwargs={'slug': self.strand.slug}),
                {'action': 'rename_strand', 'name': 'Growing Crops'},
                self.strand,
            ),
            (
                reverse('subjects:sub_strand_detail', kwargs={'slug': self.sub_strand.slug}),
                {'action': 'rename_substrand', 'name': 'Preparing the Soil'},
                self.sub_strand,
            ),
        )

        for url, data, obj in name_changes:
            with self.subTest(model=obj.__class__.__name__):
                old_slug = obj.slug
                response = self.client.post(url, data)
                self.assertRedirects(response, url)
                obj.refresh_from_db()
                self.assertEqual(obj.name, data['name'])
                self.assertEqual(obj.slug, old_slug)

    def test_non_admin_cannot_rename_strand_or_sub_strand(self):
        teacher = get_user_model().objects.create_user(
            phone='0744444451',
            password='1234',
            role=Role.TEACHER,
            first_name='Teacher',
            last_name='User',
        )
        self.client.force_login(teacher)

        strand_url = reverse('subjects:strand_detail', kwargs={'slug': self.strand.slug})
        response = self.client.post(
            strand_url,
            {'action': 'rename_strand', 'name': 'Unauthorized Strand Name'},
        )
        self.assertRedirects(response, strand_url)
        self.strand.refresh_from_db()
        self.assertEqual(self.strand.name, 'Crop Production')

        sub_strand_url = reverse(
            'subjects:sub_strand_detail',
            kwargs={'slug': self.sub_strand.slug},
        )
        response = self.client.post(
            sub_strand_url,
            {'action': 'rename_substrand', 'name': 'Unauthorized Sub-strand Name'},
        )
        self.assertRedirects(response, sub_strand_url)
        self.sub_strand.refresh_from_db()
        self.assertEqual(self.sub_strand.name, 'Planting')


class SubjectImportTests(TestCase):
    def setUp(self):
        self.grade = GradeLevel.objects.create(
            name='Grade 10',
            slug='grade-10',
            level='Senior Secondary',
        )
        self.disciplines = {
            slug: Discipline.objects.create(name=name, slug=slug)
            for name, slug in (
                ('Technical & Applied', 'technical-applied'),
                ('Creative & Psychomotor', 'creative-psychomotor'),
                ('Language & Communication', 'language-communication'),
                ('Environment & Social', 'environment-social'),
                ('Mathematics & Science', 'mathematics-science'),
                ('Religious & Moral', 'religious-moral'),
            )
        }
        self.admin = get_user_model().objects.create_user(
            phone='0744444452',
            password='1234',
            role=Role.ADMIN,
            first_name='Curriculum',
            last_name='Admin',
        )

    def test_grade_subject_parser_previews_then_creates_subjects(self):
        from subjects.models import Subject

        url = reverse('subjects:subject_list') + '?grade=grade-10'
        self.client.force_login(self.admin)
        ai_response = json.dumps({
            'subjects': [
                {'name': 'Applied Sciences', 'discipline': 'Technical & Applied'},
                {'name': 'Arts & Sports', 'discipline': 'Creative & Psychomotor'},
                {'name': 'Foreign Languages', 'discipline': 'Language & Communication'},
                {'name': 'Humanities', 'discipline': 'Environment & Social'},
                {'name': 'Languages', 'discipline': 'Language & Communication'},
                {'name': 'Pure Sciences', 'discipline': 'Mathematics & Science'},
                {'name': 'Religious Education', 'discipline': 'Religious Education'},
                {'name': 'Technical Studies', 'discipline': 'Technical & Applied'},
            ],
        })

        with patch('subjects.subject_import.OpenAIClient') as openai_client:
            openai_client.return_value.chat.return_value = ai_response
            response = self.client.post(url, {
                'action': 'parse_subjects',
                'subject_text': '## Grade 10 Designs\n\n- [Applied Sciences](https://example.test)',
            })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['subject_preview']), 8)
        self.assertContains(response, 'Review 8 subjects')
        self.assertEqual(Subject.objects.filter(grade_level=self.grade).count(), 0)

        response = self.client.post(url, {
            'action': 'import_subjects',
            'preview_token': response.context['subject_preview_token'],
        })

        self.assertRedirects(response, url)
        subjects = Subject.objects.filter(grade_level=self.grade)
        self.assertEqual(subjects.count(), 8)
        self.assertEqual(
            subjects.get(name='Applied Sciences').discipline,
            self.disciplines['technical-applied'],
        )
        self.assertEqual(
            subjects.get(name='Religious Education').discipline,
            self.disciplines['religious-moral'],
        )

    def test_subject_preview_cannot_be_applied_to_another_grade(self):
        from subjects.subject_import import (
            SubjectImportError,
            load_subject_preview,
            sign_subject_preview,
        )

        subject_data = [{
            'name': 'Applied Sciences',
            'discipline': 'Technical & Applied',
        }]
        token = sign_subject_preview(self.grade, subject_data)
        another_grade = GradeLevel.objects.create(
            name='Grade 11',
            slug='grade-11',
            level='Senior Secondary',
        )

        with self.assertRaises(SubjectImportError):
            load_subject_preview(token, another_grade)
