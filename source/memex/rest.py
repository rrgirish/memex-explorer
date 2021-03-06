import shutil
import json

from rest_framework import routers, serializers, viewsets, parsers, filters

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile, InMemoryUploadedFile
from django.core.validators import URLValidator

from base.models import Project, SeedsList
from apps.crawl_space.models import Crawl, CrawlModel


class SlugModelSerializer(serializers.ModelSerializer):
    slug = serializers.SlugField(required=False, read_only=True)


class ProjectSerializer(SlugModelSerializer):
    url = serializers.CharField(read_only=True)

    class Meta:
        model = Project


class CrawlSerializer(SlugModelSerializer):
    # Expose these fields, but only as read only.
    id = serializers.ReadOnlyField()
    seeds_list = serializers.FileField(use_url=False)
    status = serializers.CharField(read_only=True)
    config = serializers.CharField(read_only=True)
    index_name = serializers.CharField(read_only=True)
    url = serializers.CharField(read_only=True)
    pages_crawled = serializers.IntegerField(read_only=True)
    harvest_rate = serializers.FloatField(read_only=True)
    location = serializers.CharField(read_only=True)

    def validate_crawler(self, value):
        if value == "ache" and not self.initial_data.get("crawl_model"):
            raise serializers.ValidationError("Ache crawls require a Crawl Model.")
        return value

    class Meta:
        model = Crawl


class CrawlModelSerializer(SlugModelSerializer):
    model = serializers.FileField(use_url=False)
    features = serializers.FileField(use_url=False)
    url = serializers.CharField(read_only=True)

    def validate_model(self, value):
        if value.name != "pageclassifier.model":
            raise serializers.ValidationError("File must be named pageclassifier.model")
        return value

    def validate_features(self, value):
        if value.name != "pageclassifier.features":
            raise serializers.ValidationError("File must be named pageclassifier.features")
        return value

    class Meta:
        model = CrawlModel


class SeedsListSerializer(SlugModelSerializer):

    def validate_seeds(self, value):
        try:
            seeds = json.loads(value)
        except ValueError:
            raise serializers.ValidationError("Seeds must be a JSON encoded string.")
        if type(seeds) != list:
            raise serializers.ValidationError("Seeds must be an array of URLs.")
        validator = URLValidator()
        for x in seeds:
            try:
                validator(x)
            except ValidationError:
                raise serializers.ValidationError("Seeds must be valid URLs.")
        return value

    class Meta:
        model = SeedsList


"""
Viewset Classes.

Filtering is provided by django-filter.

Backend settings are in common_settings.py under REST_FRAMEWORK. Setting is:
    'DEFAULT_FILTER_BACKENDS': ('rest_framework.filters.DjangoFilterBackend',)

This backend is supplied to every viewset by default. Alter query fields by adding
or removing items from filter_fields
"""
class ProjectViewSet(viewsets.ModelViewSet):
    queryset = Project.objects.all()
    serializer_class = ProjectSerializer
    filter_fields = ('id', 'slug', 'name',)


class CrawlViewSet(viewsets.ModelViewSet):
    queryset = Crawl.objects.all()
    serializer_class = CrawlSerializer
    filter_fields = ('id', 'slug', 'name', 'description', 'status', 'project',
        'crawl_model', 'crawler',)

    def create(self, request):
        if request.data.get('textseeds', False) and not request.FILES.get("seeds_list", False):
            request.data["seeds_list"] = SimpleUploadedFile(
                'seeds',
                bytes(request.data.get("textseeds")),
                'utf-8'
            )
        return super(CrawlViewSet, self).create(request)


class CrawlModelViewSet(viewsets.ModelViewSet):
    queryset = CrawlModel.objects.all()
    serializer_class = CrawlModelSerializer
    filter_fields = ('id', 'slug', 'name', 'project',)

    def destroy(self, request, pk=None):
        model = CrawlModel.objects.get(pk=pk)
        crawls = Crawl.objects.all().filter(crawl_model=pk)
        if crawls:
            message = "The Crawl Model is being used by the following Crawls and cannot be deleted: "
            raise serializers.ValidationError({
                "message": message,
                "errors": [x.name for x in crawls],
            })
        else:
            shutil.rmtree(model.get_model_path())
            return super(CrawlModelViewSet, self).destroy(request)


class SeedsListViewSet(viewsets.ModelViewSet):
    queryset = SeedsList.objects.all()
    serializer_class = SeedsListSerializer
    filter_fields = ('id', 'name', 'seeds', 'slug',)


router = routers.DefaultRouter()
router.register(r"projects", ProjectViewSet)
router.register(r"crawls", CrawlViewSet)
router.register(r"crawl_models", CrawlModelViewSet)
router.register(r"seeds_list", SeedsListViewSet)
